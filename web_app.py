from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from modules.knowledge_base import load_documents, retrieve, ask_llm
from modules.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.error_diagnoser import ErrorDiagnoser
from modules.job_submitter import (
    register_existing_vasp_job_from_text,
    prepare_submit_script,
    prepare_vasp_submit_script,
    submit_prepared_script,
    submit_prepared_vasp_script,
)
from modules.vasp_assistant import generate_vasp_sbatch_script
from modules.job_query import (
    execute_cleanup_remote_jobs,
    extract_job_id,
    prepare_cleanup_all_remote_jobs,
    prepare_cleanup_remote_job,
    query_remote_agent_jobs,
    query_job_error,
    query_job_output,
    query_job_status,
)
from modules.router import detect_intent


app = FastAPI(title="HPC Agent Web")

documents, sources = load_documents()
diagnoser = ErrorDiagnoser()
pending_submission = {
    "kind": None,
    "script": None,
    "source_text": None,
    "uploaded_files": [],
}
pending_cleanup = {
    "kind": None,
    "targets": [],
    "job_id": None,
}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home():
    return FileResponse("static/index.html")


async def parse_chat_request(request: Request):
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_files = []
        total_size = 0

        for key, value in form.multi_items():
            if key != "files" or not getattr(value, "filename", ""):
                continue

            content = await value.read()
            total_size += len(content)

            if total_size > MAX_UPLOAD_BYTES:
                raise ValueError("上传文件总大小超过 100 MB，请减少文件数量或压缩后再上传。")

            uploaded_files.append({
                "name": value.filename,
                "content": content,
            })

        return str(form.get("message", "")), uploaded_files

    data = await request.json()
    return str(data.get("message", "")), []


def clear_pending_submission():
    pending_submission["kind"] = None
    pending_submission["script"] = None
    pending_submission["source_text"] = None
    pending_submission["uploaded_files"] = []


def clear_pending_cleanup():
    pending_cleanup["kind"] = None
    pending_cleanup["targets"] = []
    pending_cleanup["job_id"] = None


def format_uploaded_files(uploaded_files):
    if not uploaded_files:
        return ""

    return "\n".join(f"- {item['name']} ({len(item['content'])} bytes)" for item in uploaded_files)


def prepare_vasp_submission_preview(source_text: str, selector_text: str = ""):
    prepared = prepare_vasp_submit_script(source_text)

    if not prepared["ready"]:
        return prepared["message"]

    pending_submission["kind"] = "vasp"
    pending_submission["script"] = prepared["script"]
    pending_submission["source_text"] = selector_text or source_text
    pending_submission["uploaded_files"] = []

    return (
        f"{prepared['message']}\n\n"
        "回复“确认提交”后，我会连接超算执行 sbatch。\n"
        "回复“取消提交”可以放弃本次提交。"
    )


@app.post("/chat")
async def chat(request: Request):
    try:
        raw_question, uploaded_files = await parse_chat_request(request)
    except ValueError as error:
        return {
            "intent": "upload_error",
            "answer": str(error),
        }

    question = raw_question.strip()

    if not question:
        return {
            "intent": "empty",
            "answer": "请输入问题。"
        }

    normalized_question = question.lower().replace(" ", "")

    if pending_cleanup["kind"]:
        if normalized_question in {"取消", "取消清理", "no", "n", "cancel"}:
            clear_pending_cleanup()

            return {
                "intent": "cleanup_remote_jobs",
                "answer": "已取消清理。"
            }

        required_confirmation = (
            "确认清理全部"
            if pending_cleanup["kind"] == "all"
            else "确认清理"
        )

        if normalized_question == required_confirmation:
            answer = execute_cleanup_remote_jobs(pending_cleanup["targets"])
            cleanup_intent = (
                "cleanup_all_remote_jobs"
                if pending_cleanup["kind"] == "all"
                else "cleanup_remote_job"
            )
            clear_pending_cleanup()

            return {
                "intent": cleanup_intent,
                "answer": answer,
            }

        return {
            "intent": "cleanup_remote_jobs",
            "answer": (
                "当前有一个远端普通作业清理操作正在等待确认。\n\n"
                f"如要继续，请回复：{required_confirmation}\n"
                "如要放弃，请回复：取消清理"
            ),
        }

    if pending_submission["script"] and normalized_question in {
        "确认",
        "确认提交",
        "yes",
        "y",
        "submit",
    }:
        submission_kind = pending_submission["kind"]
        pending_uploaded_files = pending_submission.get("uploaded_files", [])

        if submission_kind == "vasp":
            result = submit_prepared_vasp_script(
                pending_submission["script"],
                pending_submission["source_text"] or "",
            )
        else:
            result = submit_prepared_script(
                pending_submission["script"],
                uploaded_files=pending_uploaded_files + uploaded_files,
            )

        clear_pending_submission()

        return {
            "intent": "submit_vasp_job" if submission_kind == "vasp" else "submit_job",
            "answer": result["answer"]
        }

    if pending_submission["script"] and normalized_question in {
        "取消",
        "取消提交",
        "no",
        "n",
        "cancel",
    }:
        clear_pending_submission()

        return {
            "intent": "submit_job",
            "answer": "已取消提交。"
        }

    intent = detect_intent(question)

    if intent == "submit_job":
        prepared = prepare_submit_script(question)

        if prepared["ready"]:
            pending_submission["kind"] = "generic"
            pending_submission["script"] = prepared["script"]
            pending_submission["source_text"] = question
            pending_submission["uploaded_files"] = uploaded_files

            uploaded_note = ""
            if uploaded_files:
                uploaded_note = (
                    "\n\n本次提交将一并上传这些附件到同一个远程作业目录：\n"
                    f"{format_uploaded_files(uploaded_files)}"
                )

            answer = (
                f"{prepared['message']}\n\n"
                f"{uploaded_note}"
                "\n\n"
                "回复“确认提交”后，我会连接超算执行 sbatch。\n"
                "回复“取消提交”可以放弃本次提交。"
            )
        else:
            answer = prepared["message"]

    elif intent == "submit_vasp_job":
        upload_note = ""
        if uploaded_files:
            upload_note = "\n\n提示：VASP 作业仍使用本地 VASP 输入目录流程，本次网页附件不会用于 VASP 提交。"

        answer = prepare_vasp_submission_preview(question) + upload_note

    elif intent == "register_vasp_job":
        result = register_existing_vasp_job_from_text(question)
        answer = result["message"]

    elif intent == "generate_sbatch":
        answer = generate_sbatch_script(question)

    elif intent == "generate_vasp_job":
        answer = generate_vasp_sbatch_script(question)

    elif intent in {"job_status", "job_output", "job_error"}:
        job_id = extract_job_id(question)

        if not job_id:
            answer = "请提供 job_id，例如：查看 11814709 的状态。"
        elif intent == "job_status":
            answer = query_job_status(job_id)
        elif intent == "job_output":
            answer = query_job_output(job_id)
        else:
            answer = query_job_error(job_id)

    elif intent == "list_remote_jobs":
        answer = query_remote_agent_jobs()

    elif intent == "cleanup_remote_job":
        job_id = extract_job_id(question)

        if not job_id:
            answer = "请提供要清理的 Job ID，例如：清理远端作业 11817627 的文件。"
        else:
            prepared = prepare_cleanup_remote_job(job_id)

            if prepared["ready"]:
                pending_cleanup["kind"] = "job"
                pending_cleanup["targets"] = prepared["targets"]
                pending_cleanup["job_id"] = job_id

            answer = prepared["message"]

    elif intent == "cleanup_all_remote_jobs":
        prepared = prepare_cleanup_all_remote_jobs()

        if prepared["ready"]:
            pending_cleanup["kind"] = "all"
            pending_cleanup["targets"] = prepared["targets"]
            pending_cleanup["job_id"] = None

        answer = prepared["message"]

    elif intent == "suggest_params":
        answer = suggest_slurm_parameters(question)

    elif intent == "diagnose_error":
        results = diagnoser.diagnose(question)
        answer = diagnoser.format_results(results)

    else:
        retrieved_docs = retrieve(question, documents, sources)
        answer = ask_llm(question, retrieved_docs)

    if uploaded_files and intent != "submit_job":
        answer += "\n\n提示：网页附件目前只会随普通 Slurm 提交任务上传。"

    return {
        "intent": intent,
        "answer": answer
    }
