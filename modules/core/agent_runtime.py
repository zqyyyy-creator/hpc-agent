from dataclasses import dataclass, field
from typing import Any

from modules.knowledge.knowledge_base import ask_llm, retrieve
from modules.core.environment_status import (
    check_hpc_environment,
    format_current_model_and_config,
    format_hpc_environment_check,
)
from modules.routing.router import get_clarification
from modules.slurm.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.routing.tool_dispatcher import dispatch_tool_request
from modules.vasp.vasp_assistant import generate_vasp_sbatch_script
from modules.vasp.vasp_input_generator import generate_vasp_inputs_from_potcar_request
from modules.slurm.job_query import (
    analyze_vasp_job,
    diagnose_job_request,
    extract_job_id,
    generate_vasp_report,
    query_remote_agent_jobs,
    query_remote_vasp_jobs,
)
from modules.slurm.job_lifecycle import (
    build_archive_job_records_preview,
    build_restore_job_records_preview,
    format_job_detail_for_request,
    format_job_record_archives,
    format_job_record_status,
    format_recent_jobs,
    format_vasp_jobs,
)


ANSWER_INTENTS = {
    "rag_qa",
    "clarify",
    "generate_sbatch",
    "current_config",
    "check_hpc_config",
    "generate_vasp_job",
    "generate_vasp_inputs",
    "generate_vasp_report",
    "analyze_vasp_job",
    "list_remote_jobs",
    "list_remote_vasp_jobs",
    "suggest_params",
    "diagnose_error",
    "diagnose_job",
    "troubleshoot_job",
    "register_vasp_job",
    "sync_vasp_output",
    "job_status",
    "job_output",
    "job_error",
    "recent_jobs",
    "job_record_status",
    "preview_archive_job_records",
    "list_job_record_archives",
    "preview_restore_job_records",
    "job_detail",
    "list_local_vasp_jobs",
}

CLEANUP_PREVIEW_INTENTS = {
    "cleanup_remote_job",
    "cleanup_all_remote_jobs",
    "cleanup_remote_vasp_job",
    "cleanup_all_remote_vasp_jobs",
}

CLEANUP_PENDING_KINDS = {
    "cleanup_remote_job": "job",
    "cleanup_all_remote_jobs": "all",
    "cleanup_remote_vasp_job": "vasp_job",
    "cleanup_all_remote_vasp_jobs": "vasp_all",
}

CLEANUP_PENDING_DESCRIPTIONS = {
    "cleanup_remote_job": "远端清理预览，回复“确认执行”或“确认清理”后执行。",
    "cleanup_all_remote_jobs": "远端全部清理预览，回复“确认执行”或“确认清理全部”后执行。",
    "cleanup_remote_vasp_job": "远端 VASP 清理预览，回复“确认执行”或“确认清理”后执行。",
    "cleanup_all_remote_vasp_jobs": "远端 VASP 全部清理预览，回复“确认执行”或“确认清理全部”后执行。",
}

SUBMIT_PREVIEW_INTENTS = {"submit_job", "submit_vasp_job", "test_hpc_submission"}


def can_preview_submit_intent(intent: str) -> bool:
    return intent in SUBMIT_PREVIEW_INTENTS


@dataclass
class AgentRuntimeResult:
    handled: bool
    intent: str
    answer: str = ""
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)


def can_answer_intent(intent: str) -> bool:
    return intent in ANSWER_INTENTS


def can_preview_cleanup_intent(intent: str) -> bool:
    return intent in CLEANUP_PREVIEW_INTENTS


def _cleanup_pending_payload(intent: str, dispatch_data: dict[str, Any]) -> dict[str, Any]:
    job_id = dispatch_data.get("job_id")

    if intent == "cleanup_remote_vasp_job":
        job_id = dispatch_data.get("selector")

    if intent in {"cleanup_all_remote_jobs", "cleanup_all_remote_vasp_jobs"}:
        job_id = None

    return {
        "kind": CLEANUP_PENDING_KINDS[intent],
        "targets": dispatch_data.get("targets", []),
        "job_id": job_id,
    }


def execute_cleanup_preview(question: str, intent: str, *, state) -> AgentRuntimeResult:
    if not can_preview_cleanup_intent(intent):
        return AgentRuntimeResult(handled=False, intent=intent, success=False)

    dispatch_result = dispatch_tool_request(question, intent, state=state)
    data = dict(dispatch_result.data)
    pending_cleanup = (
        _cleanup_pending_payload(intent, data)
        if data.get("ready")
        else None
    )

    data["pending_cleanup"] = pending_cleanup
    data["pending_action_description"] = CLEANUP_PENDING_DESCRIPTIONS[intent]
    data["requires_confirmation"] = bool(pending_cleanup)

    return AgentRuntimeResult(
        True,
        intent,
        dispatch_result.message,
        success=dispatch_result.success,
        data=data,
    )


def _format_file_list(uploaded_files: list[dict[str, Any]], prefix: str) -> str:
    if not uploaded_files:
        return ""

    return prefix + "\n".join(
        f"- {item['name']} ({len(item['content'])} bytes)"
        for item in uploaded_files
    )


def execute_submit_preview(
    question: str,
    intent: str,
    *,
    state,
    uploaded_files: list[dict[str, Any]] | None = None,
    source_text: str | None = None,
    inferred_command: str | None = None,
    recommendation_details: list[str] | None = None,
    auto_analyze: bool = False,
    pending_kind: str | None = None,
    confirmation_text: str = "\n\n回复“确认提交”后，我会连接超算执行 sbatch。\n回复“取消提交”可以放弃本次提交。",
    uploaded_note_prefix: str = "\n\n将上传附件:\n",
) -> AgentRuntimeResult:
    if not can_preview_submit_intent(intent):
        return AgentRuntimeResult(handled=False, intent=intent, success=False)

    uploaded_files = list(uploaded_files or [])
    dispatch_intent = "submit_job" if intent == "test_hpc_submission" else intent
    dispatch_question = question

    dispatch_result = dispatch_tool_request(
        dispatch_question,
        dispatch_intent,
        state=state,
        uploaded_files=uploaded_files,
        source_text=source_text or dispatch_question,
    )
    prepared = dispatch_result.data["prepared"]
    data = dict(dispatch_result.data)

    if not prepared.get("ready"):
        data["pending_submission"] = None
        data["requires_confirmation"] = False
        return AgentRuntimeResult(
            True,
            intent,
            prepared.get("message", ""),
            success=False,
            data=data,
        )

    if intent == "submit_vasp_job":
        pending_submission = {
            "kind": pending_kind or "vasp",
            "script": data["script"],
            "source_text": data["source_text"],
            "uploaded_files": data["uploaded_files"],
            "auto_analyze": auto_analyze,
        }
        workflow_note = ""
        if auto_analyze:
            workflow_note = (
                "\n\n检测到“运行并分析”请求。确认提交后将自动进入长流程："
                "\n监控 Slurm/VASP 输出 -> 作业结束后同步输出 -> 调用 Claude Code 生成报告。"
            )
        answer = f"{prepared['message']}{workflow_note}{confirmation_text}"
    else:
        pending_submission = {
            "kind": pending_kind or "slurm",
            "script": data["script"],
            "uploaded_files": data["uploaded_files"],
            "source_text": data["source_text"],
        }
        command_note = f"\n\n推断运行命令: {inferred_command}" if inferred_command else ""
        resource_note = ""
        if recommendation_details:
            resource_note = "\n\nAgent 推荐资源:\n" + "\n".join(
                f"- {item}" for item in recommendation_details
            )
        uploaded_note = _format_file_list(data["uploaded_files"], uploaded_note_prefix)
        intro = ""
        if intent == "test_hpc_submission":
            intro = (
                "我将用一个最小 hostname 作业测试普通 Slurm 提交流程。"
                "这只会提交一个短作业，用来验证 sbatch、远端目录和日志链路。\n\n"
            )
        answer = f"{intro}{prepared['message']}{command_note}{resource_note}{uploaded_note}{confirmation_text}"

    data["pending_submission"] = pending_submission
    data["requires_confirmation"] = True
    data["pending_action_description"] = "作业提交预览，回复“确认执行”或“确认提交”后执行。"

    return AgentRuntimeResult(
        True,
        intent,
        answer,
        success=True,
        data=data,
    )


def execute_answer_intent(
    question: str,
    intent: str,
    *,
    documents,
    sources,
    diagnoser,
    state,
    no_docs_message: str | None = None,
    current_job_id: str | None = None,
) -> AgentRuntimeResult:
    if not can_answer_intent(intent):
        return AgentRuntimeResult(handled=False, intent=intent, success=False)

    if intent == "clarify":
        return AgentRuntimeResult(True, intent, get_clarification(question), success=False)

    if intent == "generate_sbatch":
        return AgentRuntimeResult(True, intent, generate_sbatch_script(question))

    if intent == "current_config":
        return AgentRuntimeResult(True, intent, format_current_model_and_config())

    if intent == "check_hpc_config":
        result = check_hpc_environment()
        return AgentRuntimeResult(
            True,
            intent,
            format_hpc_environment_check(result),
            success=result["success"],
            data=result,
        )

    if intent == "generate_vasp_job":
        return AgentRuntimeResult(True, intent, generate_vasp_sbatch_script(question))

    if intent == "generate_vasp_inputs":
        result = generate_vasp_inputs_from_potcar_request(question)
        return AgentRuntimeResult(
            True,
            intent,
            result["message"],
            success=result["success"],
            data=result,
        )

    if intent == "generate_vasp_report":
        return AgentRuntimeResult(True, intent, generate_vasp_report(question))

    if intent == "analyze_vasp_job":
        return AgentRuntimeResult(True, intent, analyze_vasp_job(question))

    if intent == "list_remote_jobs":
        return AgentRuntimeResult(True, intent, query_remote_agent_jobs())

    if intent == "list_remote_vasp_jobs":
        return AgentRuntimeResult(True, intent, query_remote_vasp_jobs())

    if intent == "recent_jobs":
        return AgentRuntimeResult(True, intent, format_recent_jobs())

    if intent == "job_record_status":
        return AgentRuntimeResult(True, intent, format_job_record_status())

    if intent == "preview_archive_job_records":
        preview = build_archive_job_records_preview(question)
        data = dict(preview)
        pending_action = None
        if preview.get("requires_confirmation"):
            pending_action = {
                "kind": "archive_job_records",
                "payload": {
                    "keep_count": preview.get("keep_count"),
                    "keep_job_ids": preview.get("keep_job_ids") or [],
                    "archive_job_ids": preview.get("archive_job_ids") or [],
                },
                "description": "本地作业记录归档预览，回复“确认归档本地作业记录”后执行。",
            }
        data["pending_action"] = pending_action
        return AgentRuntimeResult(
            True,
            intent,
            preview["message"],
            success=preview.get("success", True),
            data=data,
        )

    if intent == "list_job_record_archives":
        return AgentRuntimeResult(True, intent, format_job_record_archives())

    if intent == "preview_restore_job_records":
        preview = build_restore_job_records_preview(question)
        data = dict(preview)
        pending_action = None
        if preview.get("requires_confirmation"):
            pending_action = {
                "kind": "restore_job_records",
                "payload": {
                    "archive_path": preview.get("archive_path"),
                    "restore_job_ids": preview.get("restore_job_ids") or [],
                },
                "description": "本地作业记录恢复预览，回复“确认恢复本地作业记录归档”后执行。",
            }
        data["pending_action"] = pending_action
        return AgentRuntimeResult(
            True,
            intent,
            preview["message"],
            success=preview.get("success", True),
            data=data,
        )

    if intent == "job_detail":
        return AgentRuntimeResult(True, intent, format_job_detail_for_request(question, state=state))

    if intent == "list_local_vasp_jobs":
        return AgentRuntimeResult(True, intent, format_vasp_jobs())

    if intent == "suggest_params":
        return AgentRuntimeResult(True, intent, suggest_slurm_parameters(question))

    if intent == "diagnose_error":
        return AgentRuntimeResult(
            True,
            intent,
            diagnoser.format_results(diagnoser.diagnose(question)),
        )

    if intent == "diagnose_job":
        return AgentRuntimeResult(True, intent, diagnose_job_request(question, state=state))

    if intent in {"register_vasp_job", "sync_vasp_output", "job_status", "job_output", "job_error"}:
        if current_job_id and intent in {"job_status", "job_output", "job_error"} and not extract_job_id(question):
            state.record_job(current_job_id, metadata={"source": "ui_context"})

        dispatch_result = dispatch_tool_request(question, intent, state=state)
        data = dict(dispatch_result.data)

        if intent in {"job_output", "job_error"}:
            data["live_log"] = dispatch_result.message[-3000:]

        return AgentRuntimeResult(
            True,
            intent,
            dispatch_result.message,
            success=dispatch_result.success,
            data=data,
        )

    docs = retrieve(question, documents, sources)
    if not docs and no_docs_message is not None:
        return AgentRuntimeResult(True, intent, no_docs_message, success=False)

    return AgentRuntimeResult(
        True,
        intent,
        ask_llm(question, docs, conversation_state=state),
    )
