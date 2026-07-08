from dataclasses import dataclass, field
from typing import Any, Callable

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE, ConversationState
from modules.knowledge.error_case_manager import REAL_CASES_PATH, append_real_case
from modules.slurm.job_lifecycle import archive_job_records, restore_job_records
from modules.slurm.job_query import execute_cleanup_remote_jobs
from modules.slurm.job_submitter import submit_prepared_script, submit_prepared_vasp_script
from modules.vasp.vasp_input_generator import generate_vasp_inputs_from_potcar


@dataclass
class ConfirmedActionResult:
    success: bool
    message: str
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


ConfirmedActionExecutors = dict[str, Callable[..., Any]]


def execute_confirmed_action(
    kind: str,
    payload: dict[str, Any],
    *,
    state: ConversationState | None = None,
    executors: ConfirmedActionExecutors | None = None,
) -> ConfirmedActionResult:
    active_state = state or GLOBAL_CONVERSATION_STATE
    active_executors = executors or {}

    if kind == "submit":
        executor = active_executors.get("submit", submit_prepared_script)
        result = executor(
            payload.get("script", ""),
            uploaded_files=payload.get("uploaded_files") or [],
        )
        success = bool(result.get("success"))
        job_id = result.get("job_id")
        remote_workdir = result.get("raw", {}).get("remote_workdir")

        if job_id:
            active_state.record_job(job_id, remote_workdir, {"kind": "slurm", "source": "submit"})

        return ConfirmedActionResult(
            success=success,
            message=result.get("answer", ""),
            kind=kind,
            data={
                "job_id": job_id,
                "remote_workdir": remote_workdir,
                "submission_kind": "slurm",
            },
            raw=result,
        )

    if kind == "submit_vasp":
        executor = active_executors.get("submit_vasp", submit_prepared_vasp_script)
        result = executor(
            payload.get("script", ""),
            payload.get("source_text", ""),
            run_name=payload.get("run_name"),
        )
        success = bool(result.get("success"))
        job_id = result.get("job_id")
        remote_workdir = result.get("raw", {}).get("remote_workdir")

        if job_id:
            active_state.record_job(
                job_id,
                remote_workdir,
                {"kind": "vasp", "type": "vasp", "source": "submit"},
            )

        return ConfirmedActionResult(
            success=success,
            message=result.get("answer", ""),
            kind=kind,
            data={
                "job_id": job_id,
                "remote_workdir": remote_workdir,
                "submission_kind": "vasp",
            },
            raw=result,
        )

    if kind == "cleanup":
        executor = active_executors.get("cleanup", execute_cleanup_remote_jobs)
        answer = executor(payload.get("targets") or [])

        return ConfirmedActionResult(
            success=True,
            message=answer,
            kind=kind,
            data={
                "targets": payload.get("targets") or [],
                "cleanup_kind": payload.get("kind"),
            },
            raw=answer,
        )

    if kind == "archive_job_records":
        executor = active_executors.get("archive_job_records", archive_job_records)
        result = executor(payload)
        return ConfirmedActionResult(
            success=bool(result.get("success")),
            message=result.get("message", ""),
            kind=kind,
            data={
                "archive_path": result.get("archive_path"),
                "archived_count": result.get("archived_count"),
                "remaining_count": result.get("remaining_count"),
                "archived_job_ids": result.get("archived_job_ids") or [],
            },
            raw=result,
        )

    if kind == "restore_job_records":
        executor = active_executors.get("restore_job_records", restore_job_records)
        result = executor(payload)
        return ConfirmedActionResult(
            success=bool(result.get("success")),
            message=result.get("message", ""),
            kind=kind,
            data={
                "archive_path": result.get("archive_path"),
                "restored_count": result.get("restored_count"),
                "skipped_count": result.get("skipped_count"),
                "missing_count": result.get("missing_count"),
                "restored_job_ids": result.get("restored_job_ids") or [],
            },
            raw=result,
        )

    if kind == "add_error_case":
        executor = active_executors.get("add_error_case", append_real_case)
        result = executor(
            payload.get("case") or {},
            path=payload.get("path") or REAL_CASES_PATH,
        )
        return ConfirmedActionResult(
            success=bool(result.get("success")),
            message=result.get("message", ""),
            kind=kind,
            data={
                "case_id": (result.get("case") or {}).get("id"),
                "path": result.get("path") or payload.get("path"),
            },
            raw=result,
        )

    if kind == "generate_vasp_inputs_overwrite":
        executor = active_executors.get("generate_vasp_inputs_overwrite", generate_vasp_inputs_from_potcar)
        result = executor(
            payload.get("job_dir", ""),
            user_request=f"{payload.get('user_request', '')} 覆盖已有配置文件",
        )
        return ConfirmedActionResult(
            success=bool(result.get("success")),
            message=result.get("message", ""),
            kind=kind,
            data={
                "job_dir": result.get("job_dir"),
                "written_files": result.get("written_files") or [],
            },
            raw=result,
        )

    return ConfirmedActionResult(
        success=False,
        message=f"不支持的确认动作: {kind}",
        kind=kind,
    )
