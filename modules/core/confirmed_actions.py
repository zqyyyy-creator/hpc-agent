from dataclasses import dataclass, field
from typing import Any, Callable

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE, ConversationState
from modules.slurm.job_lifecycle import archive_job_records, restore_job_records
from modules.slurm.job_query import execute_cleanup_remote_jobs
from modules.slurm.job_submitter import submit_prepared_script, submit_prepared_vasp_script


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

    return ConfirmedActionResult(
        success=False,
        message=f"不支持的确认动作: {kind}",
        kind=kind,
    )
