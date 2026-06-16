def is_monitor_request(text: str, job_id: str | None):
    normalized = text.lower().replace(" ", "")
    return (
        ("监控" in normalized or "monitor" in normalized)
        and "取消监控" not in normalized
        and "cancelmonitor" not in normalized
        and job_id
    )


def is_cancel_monitor_request(text: str, job_id: str | None):
    normalized = text.lower().replace(" ", "")
    return (
        ("取消监控" in normalized or "cancelmonitor" in normalized)
        and job_id
    )


def active_monitor_job_id(monitored_job_ids: list[str], active_monitor_index: int):
    if not monitored_job_ids:
        return None

    return monitored_job_ids[active_monitor_index % len(monitored_job_ids)]


def remove_monitored_job_state(
    monitored_job_ids: list[str],
    monitor_snapshots: dict,
    monitor_active: dict,
    active_monitor_index: int,
    job_id: str,
):
    if job_id not in monitored_job_ids:
        return active_monitor_index

    removed_index = monitored_job_ids.index(job_id)
    monitored_job_ids.remove(job_id)
    monitor_snapshots.pop(job_id, None)
    monitor_active.pop(job_id, None)

    if not monitored_job_ids:
        return 0

    if active_monitor_index > removed_index:
        return active_monitor_index - 1

    if active_monitor_index >= len(monitored_job_ids):
        return len(monitored_job_ids) - 1

    return active_monitor_index


def active_refresh_job_ids(monitored_job_ids: list[str], monitor_active: dict):
    return [
        job_id
        for job_id in monitored_job_ids
        if monitor_active.get(job_id, True)
    ]


def analyzing_workflow_job_ids(monitored_job_ids: list[str], vasp_workflows: dict):
    return [
        job_id
        for job_id in monitored_job_ids
        if vasp_workflows.get(str(job_id), {}).get("state") == "analyzing"
    ]
