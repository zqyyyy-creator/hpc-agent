from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from modules.knowledge_base import load_documents, retrieve, ask_llm
from modules.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.error_diagnoser import ErrorDiagnoser
from modules.job_submitter import (
    create_vasp_inputs_from_text,
    generate_vasp_template_inputs,
    import_vasp_inputs_from_text,
    register_existing_vasp_job_from_text,
    prepare_submit_script,
    prepare_vasp_submit_script,
    submit_prepared_script,
    submit_prepared_vasp_script,
)
from modules.vasp_assistant import generate_vasp_sbatch_script
from modules.job_query import (
    extract_job_id,
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
}

app.mount("/static", StaticFiles(directory="static"), name="static")


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.post("/chat")
def chat(request: ChatRequest):
    question = request.message.strip()

    if not question:
        return {
            "intent": "empty",
            "answer": "请输入问题。"
        }

    normalized_question = question.lower().replace(" ", "")

    if pending_submission["script"] and normalized_question in {
        "确认",
        "确认提交",
        "yes",
        "y",
        "submit",
    }:
        submission_kind = pending_submission["kind"]

        if submission_kind == "vasp":
            result = submit_prepared_vasp_script(
                pending_submission["script"],
                pending_submission["source_text"] or "",
            )
        else:
            result = submit_prepared_script(pending_submission["script"])

        pending_submission["kind"] = None
        pending_submission["script"] = None
        pending_submission["source_text"] = None

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
        pending_submission["kind"] = None
        pending_submission["script"] = None
        pending_submission["source_text"] = None

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
            answer = (
                f"{prepared['message']}\n\n"
                "回复“确认提交”后，我会连接超算执行 sbatch。\n"
                "回复“取消提交”可以放弃本次提交。"
            )
        else:
            answer = prepared["message"]

    elif intent == "submit_vasp_job":
        prepared = prepare_vasp_submit_script(question)

        if prepared["ready"]:
            pending_submission["kind"] = "vasp"
            pending_submission["script"] = prepared["script"]
            pending_submission["source_text"] = question
            answer = (
                f"{prepared['message']}\n\n"
                "回复“确认提交”后，我会连接超算执行 sbatch。\n"
                "回复“取消提交”可以放弃本次提交。"
            )
        else:
            answer = prepared["message"]

    elif intent == "create_vasp_inputs":
        result = create_vasp_inputs_from_text(question)
        answer = result["message"]

    elif intent == "import_vasp_inputs":
        result = import_vasp_inputs_from_text(question)
        answer = result["message"]

    elif intent == "assist_vasp_inputs":
        result = generate_vasp_template_inputs(question)
        answer = result["message"]

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

    elif intent == "suggest_params":
        answer = suggest_slurm_parameters(question)

    elif intent == "diagnose_error":
        results = diagnoser.diagnose(question)
        answer = diagnoser.format_results(results)

    else:
        retrieved_docs = retrieve(question, documents, sources)
        answer = ask_llm(question, retrieved_docs)

    return {
        "intent": intent,
        "answer": answer
    }
