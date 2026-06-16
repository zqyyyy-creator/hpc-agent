import time

from modules.tui.tui_helpers import _compact_remote_dir, _last_nonempty_lines


def format_monitor_activity(job_id: str, monitor_active: dict, vasp_workflows: dict):
    workflow = vasp_workflows.get(str(job_id))

    if workflow:
        state = workflow.get("state")
        if state in {"completed", "failed"}:
            return state
        if state in {"monitoring", "running", "analyzing"}:
            return "running" if state == "monitoring" else state

    return "active" if monitor_active.get(str(job_id), True) else "stopped"


def format_workflow_status(job_id: str, vasp_workflows: dict, now: float | None = None):
    workflow = vasp_workflows.get(str(job_id))

    if not workflow:
        return ""

    now = time.time() if now is None else now
    state = workflow.get("state", "unknown")
    display_state = "running" if state == "monitoring" else state
    message = workflow.get("message") or "-"
    started_at = workflow.get("started_at", now)
    finished_at = workflow.get("finished_at")
    analysis_started_at = workflow.get("analysis_started_at")

    if finished_at:
        total_elapsed = max(0, int(finished_at - started_at))
    else:
        total_elapsed = max(0, int(now - started_at))

    lines = [
        "",
        "",
        f"Workflow: {display_state}",
        message,
        f"Workflow Elapsed: {total_elapsed}s",
    ]

    if display_state == "analyzing" and analysis_started_at:
        analysis_elapsed = max(0, int(now - analysis_started_at))
        lines.append(f"Analysis Elapsed: {analysis_elapsed}s")

    if display_state in {"completed", "failed"}:
        lines.append("Workflow Timer: stopped")

    return "\n".join(lines)


def format_vasp_diagnosis(diagnosis: dict | None):
    if not diagnosis or not diagnosis.get("is_vasp"):
        return ""

    severity = (diagnosis.get("severity") or "unknown").upper()
    summary = diagnosis.get("summary") or "暂无 VASP 诊断结论。"
    issues = diagnosis.get("issues") or []
    evidence = diagnosis.get("evidence") or []
    recommendations = diagnosis.get("recommendations") or []

    lines = [
        "",
        "",
        f"VASP Diagnosis: {severity}",
        summary,
    ]

    if issues:
        lines.append("Issues:")
        for issue in issues[:3]:
            lines.append(f"- {issue.get('summary')}")

    if evidence:
        lines.append("Evidence:")
        for item in evidence[:4]:
            lines.append(f"- {item}")

    if recommendations:
        lines.append("Advice:")
        for item in recommendations[:2]:
            lines.append(f"- {item}")

    return "\n".join(lines)


def format_monitor_snapshot(
    snapshot: dict,
    position: int,
    total: int,
    monitor_active: dict,
    vasp_workflows: dict,
    now: float | None = None,
):
    now = time.time() if now is None else now
    remote_workdir = snapshot.get("remote_workdir") or "-"
    squeue_error = snapshot.get("squeue_error", "").strip()
    sacct_error = snapshot.get("sacct_error", "").strip()
    state = snapshot.get("state") or "UNKNOWN"
    elapsed = snapshot.get("elapsed") or "-"

    workflow = vasp_workflows.get(str(snapshot["job_id"]))
    if workflow:
        workflow_state = workflow.get("state", "unknown")
        if workflow_state == "analyzing":
            state = "ANALYZING"
            analysis_started = workflow.get("analysis_started_at") or workflow.get("started_at", now)
            elapsed = f"{max(0, int(now - analysis_started))}s"
        elif workflow_state == "completed":
            state = "COMPLETED"
            total_elapsed = max(0, int((workflow.get("finished_at") or now) - (workflow.get("started_at") or now)))
            elapsed = f"{total_elapsed}s"
        elif workflow_state == "failed":
            state = "FAILED"
            total_elapsed = max(0, int((workflow.get("finished_at") or now) - (workflow.get("started_at") or now)))
            elapsed = f"{total_elapsed}s"

    failure_note = ""
    if snapshot.get("failure_detected") and not snapshot.get("is_completed"):
        failure_note = (
            "\n\n检测到失败/异常信号。可输入："
            f"\n读取 {snapshot['job_id']} 的错误日志"
            "\n或粘贴错误日志让 Agent 诊断。"
        )

    error_note = ""
    if squeue_error:
        error_note += f"\n\nsqueue 错误:\n{squeue_error}"
    if sacct_error:
        error_note += f"\n\nsacct 错误:\n{sacct_error}"

    log_text = snapshot.get("log_output", "").strip()
    log_error = snapshot.get("log_error", "").strip()

    if log_error:
        log_text += f"\n\n读取日志错误:\n{log_error}"

    compact_dir = _compact_remote_dir(remote_workdir)
    output_preview = _last_nonempty_lines(log_text, limit=5) or "还没有找到 stdout/stderr 日志。"
    active_text = format_monitor_activity(snapshot["job_id"], monitor_active, vasp_workflows)
    workflow_section = format_workflow_status(snapshot["job_id"], vasp_workflows, now=now)
    vasp_section = format_vasp_diagnosis(snapshot.get("vasp_diagnosis"))
    return (
        f"Monitor: {position}/{total}  {active_text}\n"
        f"Job: {snapshot['job_id']}\n"
        f"State: {state}\n"
        f"Elapsed: {elapsed}\n"
        f"Dir: {compact_dir}"
        f"{workflow_section}"
        f"{vasp_section}"
        f"{failure_note}"
        f"{error_note}"
        f"\n\nLast Output:\n{output_preview}"
    )
