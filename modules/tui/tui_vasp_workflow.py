import time


def create_vasp_workflow(job_id: str, now: float | None = None):
    now = time.time() if now is None else now
    return {
        "job_id": str(job_id),
        "kind": "vasp",
        "state": "running",
        "message": "VASP 作业运行中，正在持续监控 Slurm 状态和 VASP 输出。",
        "started_at": now,
        "updated_at": now,
        "analysis_started": False,
        "analysis_started_at": None,
        "finished_at": None,
        "analysis_answer": "",
    }


def is_vasp_workflow_waiting_for_terminal(vasp_workflows: dict, job_id: str):
    workflow = vasp_workflows.get(str(job_id))
    return bool(workflow and workflow.get("state") in {"monitoring", "running"})


def update_vasp_workflow_from_snapshot(vasp_workflows: dict, snapshot: dict, now: float | None = None):
    workflow = vasp_workflows.get(str(snapshot["job_id"]))

    if not workflow or workflow.get("state") not in {"monitoring", "running"}:
        return False

    diagnosis = snapshot.get("vasp_diagnosis") or {}
    if diagnosis.get("is_vasp") and diagnosis.get("severity") in {"error", "warning"}:
        workflow["message"] = (
            f"监控中，VASP 诊断: {diagnosis.get('severity')} - "
            f"{diagnosis.get('summary')}"
        )
        workflow["updated_at"] = time.time() if now is None else now
        return True

    return False


def mark_vasp_workflow_analyzing(
    vasp_workflows: dict,
    job_id: str,
    snapshot: dict,
    now: float | None = None,
):
    workflow = vasp_workflows.get(str(job_id))

    if not workflow or workflow.get("analysis_started"):
        return None

    now = time.time() if now is None else now
    workflow["state"] = "analyzing"
    workflow["analysis_started"] = True
    workflow["analysis_started_at"] = now
    workflow["updated_at"] = now
    terminal_state = snapshot.get("state") or snapshot.get("accounting_state") or "UNKNOWN"
    workflow["message"] = (
        f"Slurm 状态为 {terminal_state}，正在同步远端输出并生成 Claude Code 报告。"
    )
    return terminal_state


def apply_vasp_workflow_analysis_result(
    vasp_workflows: dict,
    result: dict,
    now: float | None = None,
):
    job_id = str(result["job_id"])
    workflow = vasp_workflows.get(job_id)

    if not workflow:
        return None

    finished_at = time.time() if now is None else now
    workflow["updated_at"] = finished_at
    workflow["finished_at"] = finished_at

    if result["success"]:
        workflow["state"] = "completed"
        workflow["message"] = "自动分析完成，报告已写入本地 analysis 目录。"
        workflow["analysis_answer"] = result["answer"]
    else:
        workflow["state"] = "failed"
        workflow["message"] = "自动分析未完成，请查看对话区错误信息。"
        workflow["analysis_answer"] = result["answer"] or result["error"]

    return workflow
