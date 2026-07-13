from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from typing import Literal

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE
from modules.core.confirmed_actions import execute_confirmed_action
from modules.core.agent_runtime import (
    can_answer_intent,
    can_preview_cleanup_intent,
    execute_answer_intent,
    execute_cleanup_preview,
    execute_submit_preview,
)
from modules.core.environment_status import check_hpc_environment, format_hpc_environment_check
from modules.core.llm_fallback import handle_llm_fallback
from modules.core.project_doctor import format_project_doctor, run_project_doctor
from modules.knowledge.error_diagnoser import ErrorDiagnoser
from modules.mcp.audit import audited
from modules.mcp.formatters import text_payload, tool_result_payload
from modules.knowledge.knowledge_base import load_documents, retrieve
from modules.routing.router import analyze_intent, expand_shortcut_command, get_clarification
from modules.skills.skill_registry import load_skill_registry
from modules.slurm.job_query import handle_cleanup_prepare_request, handle_job_query_request, handle_vasp_postprocess_request
from modules.slurm.job_submitter import prepare_submit_script, prepare_vasp_submit_script
from modules.vasp.vasp_input_generator import generate_vasp_inputs_from_potcar_request
from modules.vasp.vasp_report_context import generate_vasp_report_context


QueryType = Literal["status", "output", "error", "detail"]
CleanupType = Literal["job", "all_jobs", "vasp_job", "all_vasp_jobs"]
SubmissionKind = Literal["slurm", "vasp"]
VASP_ANALYSIS_MARKERS = {
    "OUTCAR",
    "OSZICAR",
    "vasprun.xml",
    "CONTCAR",
    "XDATCAR",
    "INCAR",
    "KPOINTS",
    "POSCAR",
}
_KNOWLEDGE_CACHE: tuple[list, list] | None = None
_DIAGNOSER: ErrorDiagnoser | None = None
_PENDING_SUBMISSION_ACTION = "mcp_pending_submission"


def _runtime_context() -> tuple[list, list, ErrorDiagnoser]:
    global _KNOWLEDGE_CACHE, _DIAGNOSER
    if _KNOWLEDGE_CACHE is None:
        _KNOWLEDGE_CACHE = load_documents()
    if _DIAGNOSER is None:
        _DIAGNOSER = ErrorDiagnoser()
    documents, sources = _KNOWLEDGE_CACHE
    return documents, sources, _DIAGNOSER


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _guarded_execution(
    *,
    confirm: bool,
    env_var: str,
    risk: str,
    action: str,
) -> dict[str, Any] | None:
    if not confirm:
        return text_payload(
            f"{action} was not executed because confirm=true was not provided.",
            ok=False,
            risk=risk,
            requires_confirmation=True,
            required_env=env_var,
        )

    if not _enabled(env_var):
        return text_payload(
            f"{action} was not executed because {env_var}=1 is not set.",
            ok=False,
            risk=risk,
            requires_confirmation=True,
            required_env=env_var,
        )

    return None


def _has_vasp_analysis_files(directory: Path) -> bool:
    return directory.is_dir() and any((directory / name).is_file() for name in VASP_ANALYSIS_MARKERS)


def _is_vasp_analysis_target(directory: Path) -> bool:
    return _has_vasp_analysis_files(directory) or _has_vasp_analysis_files(directory / "raw_output")


def _find_vasp_analysis_candidates(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []

    candidates = []
    ignored_names = {"analysis", "raw_output", "__pycache__"}

    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name in ignored_names:
            continue
        if _is_vasp_analysis_target(child):
            candidates.append(child)

    if candidates:
        return candidates

    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name in ignored_names:
            continue
        for grandchild in sorted(child.iterdir(), key=lambda item: item.name):
            if grandchild.is_dir() and grandchild.name not in ignored_names and _is_vasp_analysis_target(grandchild):
                candidates.append(grandchild)

    return candidates


def _pending_submission() -> dict[str, Any] | None:
    pending = GLOBAL_CONVERSATION_STATE.pending_action
    if not pending or pending.get("kind") != _PENDING_SUBMISSION_ACTION:
        return None
    payload = pending.get("payload") or {}
    return payload if payload.get("script") else None


def _store_pending_submission(pending_submission: dict[str, Any] | None) -> None:
    if not pending_submission:
        return

    GLOBAL_CONVERSATION_STATE.record_pending_action(
        _PENDING_SUBMISSION_ACTION,
        dict(pending_submission),
        "已准备 Slurm/VASP 提交预览。只有在用户确认且 MCP 写入开关开启后才提交。",
    )


def _clear_pending_submission() -> None:
    GLOBAL_CONVERSATION_STATE.clear_pending_action(_PENDING_SUBMISSION_ACTION)


def _looks_like_pending_submit_request(text: str) -> bool:
    normalized = text.lower().replace(" ", "")
    submit_markers = ["提交", "运行", "执行", "submit", "run"]
    reference_markers = ["刚才", "上一个", "刚刚", "这个", "那个", "预览", "脚本", "it", "that"]
    return any(marker in normalized for marker in submit_markers) and any(
        marker in normalized for marker in reference_markers
    )


def _format_chat_reply(payload: dict[str, Any]) -> str:
    message = str(payload.get("message") or "").strip()
    intent = payload.get("intent")

    if payload.get("pending_submission"):
        return (
            "已生成提交预览，尚未提交。请检查脚本；确认后我可以提交刚才这个作业。"
        )

    if intent == "generate_sbatch" and message.startswith("#!/bin/bash"):
        return "已生成 Slurm 脚本预览，尚未提交。"

    if intent == "check_hpc_config":
        return "已完成 HPC 配置检查。"

    if intent in {"job_status", "job_output", "job_error"}:
        return "已查询作业信息。"

    if len(message) > 500:
        return message[:500].rstrip() + "..."

    return message


def _next_step_for_payload(payload: dict[str, Any]) -> str | None:
    if payload.get("pending_submission"):
        return "如需提交，请明确确认；ChatGPT 应以 confirm=true 调用 hpc_agent_chat。"

    if payload.get("intent") == "generate_sbatch":
        return "如需真实提交，请先检查脚本，再确认提交。"

    if payload.get("intent") == "job_status":
        return "作业结束后可以继续查询输出或错误日志。"

    return None


def _finalize_agent_chat(
    *,
    raw_message: str,
    confirm: bool,
    payload: dict[str, Any],
) -> dict:
    payload["reply"] = _format_chat_reply(payload)
    next_step = _next_step_for_payload(payload)
    if next_step:
        payload["next_step"] = next_step

    GLOBAL_CONVERSATION_STATE.remember_turn(
        "user",
        raw_message,
        {"tool": "hpc_agent_chat", "confirm": confirm},
    )
    GLOBAL_CONVERSATION_STATE.remember_turn(
        "assistant",
        str(payload.get("reply") or payload.get("message") or ""),
        {
            "tool": "hpc_agent_chat",
            "intent": payload.get("intent"),
            "ok": payload.get("ok"),
            "risk": payload.get("risk"),
        },
    )

    return audited(
        "hpc_agent_chat",
        risk=str(payload.get("risk") or "read_only"),
        arguments={"message": raw_message, "confirm": confirm},
        result=payload,
    )


def check_install() -> dict:
    result = run_project_doctor()
    return text_payload(
        format_project_doctor(result),
        ok=bool(result.get("success")),
        sections=result.get("sections", {}),
    )


def check_config() -> dict:
    result = check_hpc_environment()
    return text_payload(
        format_hpc_environment_check(result),
        ok=bool(result.get("success")),
        checks=result.get("checks", []),
    )


def agent_chat(message: str, *, confirm: bool = False) -> dict:
    raw_message = str(message or "").strip()
    if not raw_message:
        return text_payload(
            "message is required.",
            ok=False,
            risk="read_only",
            intent="clarify",
        )

    question = expand_shortcut_command(raw_message)
    if GLOBAL_CONVERSATION_STATE.is_cancellation(question):
        _clear_pending_submission()
        payload = text_payload(
            "已取消刚才待确认的 MCP 提交预览。",
            ok=True,
            risk="read_only",
            intent="cancel_pending_submission",
            pending_submission=None,
        )
        return _finalize_agent_chat(raw_message=raw_message, confirm=confirm, payload=payload)

    pending_submission = _pending_submission()
    if pending_submission and (
        GLOBAL_CONVERSATION_STATE.is_confirmation(question)
        or _looks_like_pending_submit_request(question)
    ):
        if not confirm:
            payload = text_payload(
                (
                    "已找到刚才生成的提交预览，但还没有执行提交。"
                    "如果用户已经明确确认，请用 confirm=true 再调用 hpc_agent_chat。"
                ),
                ok=False,
                risk="write_execute",
                intent="submit_pending_job",
                pending_submission=pending_submission,
                requires_confirmation=True,
                required_env="HPC_AGENT_MCP_ENABLE_WRITE",
            )
            return _finalize_agent_chat(raw_message=raw_message, confirm=confirm, payload=payload)

        result = submit_prepared_job(
            str(pending_submission.get("script") or ""),
            (pending_submission.get("kind") or "slurm"),  # type: ignore[arg-type]
            source_text=str(pending_submission.get("source_text") or raw_message),
            run_name=pending_submission.get("run_name"),
            confirm=True,
        )
        if result.get("ok"):
            _clear_pending_submission()
        result["intent"] = "submit_pending_job"
        result["pending_submission"] = None if result.get("ok") else pending_submission
        return _finalize_agent_chat(raw_message=raw_message, confirm=confirm, payload=result)

    documents, sources, diagnoser = _runtime_context()
    decision = analyze_intent(question)
    intent = decision.intent
    result_data: dict[str, Any] = {
        "decision": {
            "intent": decision.intent,
            "risk": decision.risk,
            "reason": decision.reason,
            "matched_keywords": decision.matched_keywords,
            "needs_clarification": decision.needs_clarification,
            "clarification": decision.clarification,
        }
    }

    if intent == "clarify":
        payload = text_payload(
            get_clarification(question),
            ok=False,
            risk="read_only",
            intent=intent,
            **result_data,
        )
    elif intent in {"submit_job", "submit_vasp_job", "test_hpc_submission"}:
        runtime_result = execute_submit_preview(
            question,
            intent,
            state=GLOBAL_CONVERSATION_STATE,
            confirmation_text=(
                "\n\nThis is only a submission preview. To submit, call "
                "hpc_submit_prepared_job with confirm=true after checking the script."
            ),
        )
        data = dict(runtime_result.data)
        pending_submission = data.pop("pending_submission", None)
        data.pop("requires_confirmation", None)
        _store_pending_submission(pending_submission)
        payload = text_payload(
            runtime_result.answer,
            ok=runtime_result.success,
            risk="write_preview",
            intent=runtime_result.intent,
            pending_submission=pending_submission,
            requires_confirmation=bool(pending_submission),
            **result_data,
            **data,
        )
    elif can_preview_cleanup_intent(intent):
        runtime_result = execute_cleanup_preview(
            question,
            intent,
            state=GLOBAL_CONVERSATION_STATE,
        )
        data = dict(runtime_result.data)
        pending_cleanup = data.pop("pending_cleanup", None)
        payload = text_payload(
            runtime_result.answer,
            ok=runtime_result.success,
            risk="destructive_preview",
            intent=runtime_result.intent,
            pending_cleanup=pending_cleanup,
            requires_confirmation=bool(pending_cleanup),
            **result_data,
            **data,
        )
    elif can_answer_intent(intent):
        runtime_result = execute_answer_intent(
            question,
            intent,
            documents=documents,
            sources=sources,
            diagnoser=diagnoser,
            state=GLOBAL_CONVERSATION_STATE,
        )
        data = dict(runtime_result.data)
        payload = text_payload(
            runtime_result.answer,
            ok=runtime_result.success,
            risk=decision.risk or "read_only",
            intent=runtime_result.intent,
            **result_data,
            **data,
        )
    else:
        fallback = handle_llm_fallback(
            question,
            documents,
            sources,
            diagnoser,
            GLOBAL_CONVERSATION_STATE,
        )
        payload = text_payload(
            fallback.answer,
            ok=fallback.success,
            risk="read_only",
            intent=fallback.intent,
            source=fallback.source,
            prompt_skills=fallback.prompt_skills,
            external_skills=fallback.external_skills,
            pending_action=fallback.pending_action,
            **result_data,
        )

    return _finalize_agent_chat(raw_message=raw_message, confirm=confirm, payload=payload)


def get_cluster_info(query: str, top_k: int = 5) -> dict:
    documents, sources = load_documents()
    results = retrieve(query, documents, sources, top_k=max(1, min(top_k, 10)))
    return text_payload(
        "已检索集群知识文档。",
        ok=True,
        risk="read_only",
        query=query,
        results=results,
    )


def list_skills(include_skipped: bool = True) -> dict:
    registry = load_skill_registry()
    skills = [
        {
            "name": skill.name,
            "description": skill.description,
            "type": skill.type,
            "intents": list(skill.intents),
            "triggers": list(skill.triggers),
            "handler": skill.handler,
            "runtime": dict(skill.runtime),
            "risk": skill.risk,
            "source": skill.source,
            "path": str(skill.path),
        }
        for skill in sorted(registry.all(), key=lambda item: (item.source, item.name))
    ]
    skipped = [
        {
            "name": item.name,
            "path": str(item.path),
            "reason": item.reason,
            "source": item.source,
        }
        for item in registry.skipped()
    ] if include_skipped else []
    return text_payload(
        "已加载 hpc-agent skills。",
        ok=True,
        risk="read_only",
        skills=skills,
        skipped=skipped,
        skill_count=len(skills),
        skipped_count=len(skipped),
    )


def generate_sbatch(request: str) -> dict:
    prepared = prepare_submit_script(request)
    ok = bool(prepared.get("ready"))
    result = text_payload(
        prepared.get("message") or "",
        ok=ok,
        risk="write_preview",
        ready=ok,
        script=prepared.get("script"),
        tool_call=prepared.get("tool_call"),
        requires_confirmation=False,
        note="此 MCP 工具只生成 sbatch 脚本预览，不提交作业。",
    )
    return audited(
        "hpc_generate_sbatch",
        risk="write_preview",
        arguments={"request": request},
        result=result,
    )


def generate_sbatch_structured(
    *,
    command: str,
    nodes: int = 1,
    time_limit: str = "00:10:00",
    partition: str | None = None,
    cpus_per_task: int = 1,
    job_name: str = "hpc_agent_job",
    memory: str | None = None,
    gpu_count: int | None = None,
) -> dict:
    parts = [
        "生成 Slurm 脚本预览",
        f"command: {command}",
        f"nodes: {nodes}",
        f"time: {time_limit}",
        f"cpus: {cpus_per_task}",
        f"job_name: {job_name}",
    ]
    if partition:
        parts.append(f"partition: {partition}")
    if memory:
        parts.append(f"memory: {memory}")
    if gpu_count:
        parts.append(f"gpu: {gpu_count}")

    request = "\n".join(parts)
    prepared = prepare_submit_script(request)
    ok = bool(prepared.get("ready"))
    structured_arguments = {
        "command": command,
        "nodes": nodes,
        "time_limit": time_limit,
        "partition": partition,
        "cpus_per_task": cpus_per_task,
        "job_name": job_name,
        "memory": memory,
        "gpu_count": gpu_count,
    }
    result = text_payload(
        prepared.get("message") or "",
        ok=ok,
        risk="write_preview",
        ready=ok,
        script=prepared.get("script"),
        tool_call=prepared.get("tool_call"),
        structured_arguments=structured_arguments,
        requires_confirmation=False,
        note="此结构化 MCP 工具只生成 sbatch 脚本预览，不提交作业。",
    )
    return audited(
        "hpc_generate_sbatch_structured",
        risk="write_preview",
        arguments=structured_arguments,
        result=result,
    )


def submit_prepared_job(
    script: str,
    submission_kind: SubmissionKind = "slurm",
    *,
    source_text: str = "",
    run_name: str | None = None,
    confirm: bool = False,
) -> dict:
    blocked = _guarded_execution(
        confirm=confirm,
        env_var="HPC_AGENT_MCP_ENABLE_WRITE",
        risk="write_execute",
        action=f"{submission_kind} 作业提交",
    )
    if blocked:
        return audited(
            "hpc_submit_prepared_job",
            risk="write_execute",
            arguments={
                "submission_kind": submission_kind,
                "source_text": source_text,
                "run_name": run_name,
                "confirm": confirm,
            },
            result=blocked,
        )

    kind = "submit_vasp" if submission_kind == "vasp" else "submit"
    payload = {
        "script": script,
        "source_text": source_text,
        "run_name": run_name,
        "uploaded_files": [],
    }
    result = execute_confirmed_action(kind, payload, state=GLOBAL_CONVERSATION_STATE)
    result_payload = text_payload(
        result.message,
        ok=result.success,
        risk="write_execute",
        kind=result.kind,
        data=result.data,
        raw=result.raw,
    )
    return audited(
        "hpc_submit_prepared_job",
        risk="write_execute",
        arguments={
            "submission_kind": submission_kind,
            "source_text": source_text,
            "run_name": run_name,
            "confirm": confirm,
        },
        result=result_payload,
    )


def prepare_vasp_job(request: str) -> dict:
    prepared = prepare_vasp_submit_script(request)
    ok = bool(prepared.get("ready"))
    result = text_payload(
        prepared.get("message") or "",
        ok=ok,
        risk="write_preview",
        ready=ok,
        script=prepared.get("script"),
        local_jobs_dir=prepared.get("local_jobs_dir"),
        remote_input_dir=prepared.get("remote_input_dir"),
        remote_output_dir=prepared.get("remote_output_dir"),
        tool_call=prepared.get("tool_call"),
        requires_confirmation=False,
        note="此 MCP 工具只生成 VASP Slurm 作业预览，不提交作业，也不上传文件。",
    )
    return audited(
        "hpc_prepare_vasp_job",
        risk="write_preview",
        arguments={"request": request},
        result=result,
    )


def prepare_vasp_job_structured(
    *,
    local_input_dir: str,
    partition: str | None = None,
    nodes: int = 1,
    time_limit: str = "01:00:00",
    job_name: str | None = None,
    vasp_command: str | None = None,
    setup_command: str | None = None,
) -> dict:
    structured_arguments = {
        "local_input_dir": local_input_dir,
        "partition": partition,
        "nodes": nodes,
        "time_limit": time_limit,
        "job_name": job_name,
        "vasp_command": vasp_command,
        "setup_command": setup_command,
    }
    parts = [
        "生成 VASP Slurm 作业预览",
        f"本地 VASP 输入目录: {local_input_dir}",
        f"nodes: {nodes}",
        f"time: {time_limit}",
    ]
    if partition:
        parts.append(f"partition: {partition}")
    if job_name:
        parts.append(f"job_name: {job_name}")
    if vasp_command:
        parts.append(f"VASP command: {vasp_command}")
    if setup_command:
        parts.append(f"setup command: {setup_command}")

    result = prepare_vasp_job("\n".join(parts))
    result["structured_arguments"] = structured_arguments
    result.setdefault("data", {})["structured_arguments"] = structured_arguments
    return audited(
        "hpc_prepare_vasp_job_structured",
        risk="write_preview",
        arguments=structured_arguments,
        result=result,
    )


def generate_vasp_inputs(request: str, jobs_dir: str | None = None) -> dict:
    kwargs = {"jobs_dir": jobs_dir} if jobs_dir else {}
    result = generate_vasp_inputs_from_potcar_request(request, **kwargs)
    ok = bool(result.get("success"))
    data = dict(result)
    message = str(data.pop("message", "") or "")
    payload = text_payload(
        message,
        ok=ok,
        risk="write_local",
        **data,
    )
    return audited(
        "vasp_generate_inputs",
        risk="write_local",
        arguments={"request": request, "jobs_dir": jobs_dir},
        result=payload,
    )


def generate_vasp_inputs_structured(
    *,
    job_name: str,
    element: str | None = None,
    formula: str | None = None,
    calculation_type: str = "static",
    encut: int | None = None,
    kpoints: list[int] | None = None,
    jobs_dir: str | None = None,
    description: str = "",
    overwrite: bool = False,
) -> dict:
    structured_arguments = {
        "job_name": job_name,
        "element": element,
        "formula": formula,
        "calculation_type": calculation_type,
        "encut": encut,
        "kpoints": kpoints,
        "jobs_dir": jobs_dir,
        "description": description,
        "overwrite": overwrite,
    }
    parts = [
        "生成 VASP 输入文件",
        f"job_name: {job_name}",
        f"calculation_type: {calculation_type}",
    ]
    if element:
        parts.append(f"element: {element}")
    if formula:
        parts.append(f"formula: {formula}")
    if encut:
        parts.append(f"ENCUT: {encut}")
    if kpoints:
        parts.append("KPOINTS: " + " ".join(str(value) for value in kpoints))
    if overwrite:
        parts.append("允许覆盖已有 INCAR/KPOINTS/POSCAR")
    if description:
        parts.append(f"description: {description}")

    result = generate_vasp_inputs("\n".join(parts), jobs_dir=jobs_dir)
    result["structured_arguments"] = structured_arguments
    result.setdefault("data", {})["structured_arguments"] = structured_arguments
    return audited(
        "vasp_generate_inputs_structured",
        risk="write_local",
        arguments=structured_arguments,
        result=result,
    )


def analyze_vasp_local_result(local_job_dir: str) -> dict:
    requested_dir = Path(local_job_dir).expanduser().resolve()
    resolved_from = None

    if requested_dir.is_dir() and not _is_vasp_analysis_target(requested_dir):
        candidates = _find_vasp_analysis_candidates(requested_dir)
        if len(candidates) == 1:
            resolved_from = str(requested_dir)
            requested_dir = candidates[0]
        elif len(candidates) > 1:
            payload = text_payload(
                (
                    "提供的路径看起来是 VASP 输出集合目录，"
                    "不是单个 VASP 作业输出目录。请选择一个候选目录，"
                    "然后再次调用 vasp_analyze_local_result。"
                ),
                ok=False,
                risk="write_local",
                requested_dir=str(requested_dir),
                candidate_job_dirs=[str(path) for path in candidates],
                candidate_count=len(candidates),
                expected_input=(
                    "单个 VASP 作业目录、它的 raw_output 目录，或直接包含 "
                    "OUTCAR/OSZICAR/vasprun.xml 的目录。"
                ),
            )
            return audited(
                "vasp_analyze_local_result",
                risk="write_local",
                arguments={"local_job_dir": local_job_dir},
                result=payload,
            )

    result = generate_vasp_report_context(requested_dir)
    ok = bool(result.get("success"))
    data = dict(result)
    if resolved_from:
        data["resolved_from"] = resolved_from
    message = str(data.pop("message", "") or "")
    payload = text_payload(
        message
        or (
            "VASP 本地结果分析上下文已生成。"
            if ok
            else "VASP 本地结果分析失败。"
        ),
        ok=ok,
        risk="write_local",
        **data,
    )
    return audited(
        "vasp_analyze_local_result",
        risk="write_local",
        arguments={"local_job_dir": local_job_dir},
        result=payload,
    )


def analyze_vasp_local_result_structured(local_job_dir: str) -> dict:
    structured_arguments = {"local_job_dir": local_job_dir}
    result = analyze_vasp_local_result(local_job_dir)
    result["structured_arguments"] = structured_arguments
    result.setdefault("data", {})["structured_arguments"] = structured_arguments
    return audited(
        "vasp_analyze_local_result_structured",
        risk="write_local",
        arguments=structured_arguments,
        result=result,
    )


def sync_vasp_output(job_id: str, *, confirm: bool = False) -> dict:
    blocked = _guarded_execution(
        confirm=confirm,
        env_var="HPC_AGENT_MCP_ENABLE_WRITE",
        risk="write_execute",
        action="VASP output sync",
    )
    if blocked:
        return audited(
            "vasp_sync_output",
            risk="write_execute",
            arguments={"job_id": job_id, "confirm": confirm},
            result=blocked,
        )

    result = handle_vasp_postprocess_request(
        f"同步 VASP 作业 {job_id} 输出",
        "sync_vasp_output",
        state=GLOBAL_CONVERSATION_STATE,
    )
    payload = tool_result_payload(result, risk="write_execute")
    return audited(
        "vasp_sync_output",
        risk="write_execute",
        arguments={"job_id": job_id, "confirm": confirm},
        result=payload,
    )


def sync_vasp_output_structured(job_id: str, *, confirm: bool = False) -> dict:
    structured_arguments = {"job_id": job_id, "confirm": confirm}
    result = sync_vasp_output(job_id, confirm=confirm)
    result["structured_arguments"] = structured_arguments
    result.setdefault("data", {})["structured_arguments"] = structured_arguments
    return audited(
        "vasp_sync_output_structured",
        risk="write_execute",
        arguments=structured_arguments,
        result=result,
    )


def query_job(job_id: str, query_type: QueryType = "status") -> dict:
    intent_by_type = {
        "status": "job_status",
        "output": "job_output",
        "error": "job_error",
        "detail": "job_status",
    }
    intent = intent_by_type.get(query_type, "job_status")
    question = f"{job_id} {query_type}"
    result = handle_job_query_request(question, intent, state=GLOBAL_CONVERSATION_STATE)
    payload = tool_result_payload(result, risk="read_only")
    payload["job_id"] = job_id
    payload["query_type"] = query_type
    return payload


def query_job_structured(job_id: str, query_type: QueryType = "status") -> dict:
    structured_arguments = {"job_id": job_id, "query_type": query_type}
    result = query_job(job_id, query_type)
    result["structured_arguments"] = structured_arguments
    result.setdefault("data", {})["structured_arguments"] = structured_arguments
    return audited(
        "hpc_query_job_structured",
        risk="read_only",
        arguments=structured_arguments,
        result=result,
    )


def prepare_cleanup(request: str, cleanup_type: CleanupType = "job") -> dict:
    intent_by_type = {
        "job": "cleanup_remote_job",
        "all_jobs": "cleanup_all_remote_jobs",
        "vasp_job": "cleanup_remote_vasp_job",
        "all_vasp_jobs": "cleanup_all_remote_vasp_jobs",
    }
    intent = intent_by_type.get(cleanup_type, "cleanup_remote_job")
    result = handle_cleanup_prepare_request(request, intent)
    payload = tool_result_payload(result, risk="destructive_preview")
    return audited(
        "hpc_prepare_cleanup",
        risk="destructive_preview",
        arguments={"request": request, "cleanup_type": cleanup_type},
        result=payload,
    )


def prepare_cleanup_structured(
    *,
    cleanup_type: CleanupType = "job",
    job_id: str | None = None,
    selector: str | None = None,
    scope: str = "all",
) -> dict:
    target = selector or job_id or ""
    if cleanup_type == "all_jobs":
        request = "清理远端 hpc-agent-jobs 下所有普通 Slurm 作业文件"
    elif cleanup_type == "all_vasp_jobs":
        request = "清理远端所有 VASP 作业目录"
    elif cleanup_type == "vasp_job":
        request = f"清理远端 VASP 作业 {target} 的文件"
    else:
        request = f"清理远端作业 {target} 的文件"

    if scope and scope != "all":
        request = f"{request}，范围: {scope}"

    structured_arguments = {
        "cleanup_type": cleanup_type,
        "job_id": job_id,
        "selector": selector,
        "scope": scope,
    }
    result = prepare_cleanup(request, cleanup_type)
    result["structured_arguments"] = structured_arguments
    result.setdefault("data", {})["structured_arguments"] = structured_arguments
    return audited(
        "hpc_prepare_cleanup_structured",
        risk="destructive_preview",
        arguments=structured_arguments,
        result=result,
    )


def execute_cleanup(
    targets: list[dict[str, Any]],
    *,
    cleanup_kind: str = "",
    confirm: bool = False,
) -> dict:
    blocked = _guarded_execution(
        confirm=confirm,
        env_var="HPC_AGENT_MCP_ENABLE_DESTRUCTIVE",
        risk="destructive",
        action="remote cleanup",
    )
    if blocked:
        return audited(
            "hpc_execute_cleanup",
            risk="destructive",
            arguments={"targets": targets, "cleanup_kind": cleanup_kind, "confirm": confirm},
            result=blocked,
        )

    result = execute_confirmed_action(
        "cleanup",
        {
            "targets": targets,
            "kind": cleanup_kind or "mcp_cleanup",
        },
        state=GLOBAL_CONVERSATION_STATE,
    )
    payload = text_payload(
        result.message,
        ok=result.success,
        risk="destructive",
        kind=result.kind,
        data=result.data,
        raw=result.raw,
    )
    return audited(
        "hpc_execute_cleanup",
        risk="destructive",
        arguments={"targets": targets, "cleanup_kind": cleanup_kind, "confirm": confirm},
        result=payload,
    )
