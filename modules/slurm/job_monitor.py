import shlex

from modules.core.hpc_config import REMOTE_WORKDIR, VASP_REMOTE_OUTPUT_DIR
from modules.slurm.remote import run_remote_command


TERMINAL_FAILURE_STATES = {
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "NODE_FAIL",
    "PREEMPTED",
    "BOOT_FAIL",
}


def check_job(job_id):
    command = f"squeue -j {job_id}"
    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def check_job_accounting(job_id):
    command = (
        f"sacct -j {shlex.quote(str(job_id))} "
        "--format=JobID,JobName,State,ExitCode,Elapsed,Start,End "
        "--parsable2 --noheader"
    )
    output, error = run_remote_command(command)

    states = []
    exit_codes = []
    elapsed_values = []

    for line in output.splitlines():
        parts = line.split("|")

        if len(parts) < 5:
            continue

        states.append(parts[2].strip())
        exit_codes.append(parts[3].strip())
        elapsed_values.append(parts[4].strip())

    primary_state = states[0] if states else None
    primary_elapsed = elapsed_values[0] if elapsed_values else None

    return {
        "job_id": str(job_id),
        "output": output,
        "error": error,
        "states": states,
        "exit_codes": exit_codes,
        "elapsed_values": elapsed_values,
        "primary_state": primary_state,
        "primary_elapsed": primary_elapsed,
    }


def parse_squeue_state_elapsed(output: str):
    lines = [line for line in output.splitlines() if line.strip()]

    if len(lines) < 2:
        return None, None

    header = lines[0].split()
    values = lines[1].split()

    if len(values) < len(header):
        return None, None

    row = dict(zip(header, values))
    state = row.get("ST") or row.get("STATE")
    elapsed = row.get("TIME") or row.get("TIME_USED")

    return state, elapsed


def squeue_has_job_row(output: str) -> bool:
    return len([line for line in output.splitlines() if line.strip()]) >= 2


def validate_monitorable_job(job_id):
    status = check_job(job_id)
    state, elapsed = parse_squeue_state_elapsed(status.get("output", ""))

    if squeue_has_job_row(status.get("output", "")):
        return {
            "job_id": str(job_id),
            "monitorable": True,
            "state": state,
            "elapsed": elapsed,
            "message": "",
            "squeue_output": status.get("output", ""),
            "squeue_error": status.get("error", ""),
            "sacct_state": None,
            "sacct_error": "",
        }

    accounting = check_job_accounting(job_id)
    accounting_state = accounting.get("primary_state")

    if accounting_state:
        message = (
            f"Job {job_id} 当前不在 squeue 队列中，sacct 状态为 {accounting_state}，"
            "无法开始监控。"
        )
    else:
        message = (
            f"Job {job_id} 当前不在 squeue 队列中，也没有查到可用的 sacct 状态，"
            "无法开始监控。"
        )

    return {
        "job_id": str(job_id),
        "monitorable": False,
        "state": accounting_state,
        "elapsed": accounting.get("primary_elapsed"),
        "message": message,
        "squeue_output": status.get("output", ""),
        "squeue_error": status.get("error", ""),
        "sacct_state": accounting_state,
        "sacct_error": accounting.get("error", ""),
    }


def find_remote_job_dir(job_id: str):
    from modules.slurm.job_registry import get_job

    job = get_job(job_id)

    if job and job.get("remote_workdir"):
        return job["remote_workdir"]

    for root_dir in [REMOTE_WORKDIR, VASP_REMOTE_OUTPUT_DIR]:
        found_dir = find_remote_job_dir_under_root(job_id, root_dir)

        if found_dir:
            return found_dir

    return None


def find_remote_job_dir_under_root(job_id: str, root_dir: str):
    if not root_dir:
        return None

    safe_job_id = shlex.quote(str(job_id))
    command = (
        f"cd {shlex.quote(root_dir)} && "
        "{ "
        "find . -mindepth 2 -maxdepth 3 -type f "
        f"\\( -name '*_{safe_job_id}.out' -o -name '*_{safe_job_id}.err' \\) "
        "-printf '%h\\n'; "
        "find . -maxdepth 1 -type f "
        f"\\( -name '*_{safe_job_id}.out' -o -name '*_{safe_job_id}.err' \\) "
        "-printf '.\\n'; "
        "} | sort -u | head -n 1"
    )
    output, error = run_remote_command(command)

    if error.strip():
        return None

    relative_dir = output.strip().lstrip("./")

    if not relative_dir:
        return None

    if relative_dir == ".":
        return root_dir

    return f"{root_dir}/{relative_dir}"


def tail_job_logs(job_id: str, remote_workdir: str = None, lines: int = 50):
    remote_workdir = remote_workdir or find_remote_job_dir(job_id)

    if not remote_workdir:
        return {
            "job_id": job_id,
            "remote_workdir": None,
            "output": "",
            "error": "没有找到该 Job 对应的远端作业目录。",
        }

    safe_job_id = shlex.quote(str(job_id))
    safe_lines = max(1, min(int(lines), 500))
    command = (
        f"cd {shlex.quote(remote_workdir)} && "
        "{ "
        "echo 'STDOUT:'; "
        f"if ls *_{safe_job_id}.out >/dev/null 2>&1; then tail -n {safe_lines} *_{safe_job_id}.out; "
        f"elif ls *.out >/dev/null 2>&1; then tail -n {safe_lines} *.out; "
        "else echo 'No stdout file found yet.'; fi; "
        "echo ''; echo 'STDERR:'; "
        f"if ls *_{safe_job_id}.err >/dev/null 2>&1; then tail -n {safe_lines} *_{safe_job_id}.err; "
        f"elif ls *.err >/dev/null 2>&1; then tail -n {safe_lines} *.err; "
        "else echo 'No stderr file found yet.'; fi; "
        "}"
    )
    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "remote_workdir": remote_workdir,
        "output": output,
        "error": error,
    }


def get_job_monitor_snapshot(job_id: str, lines: int = 50):
    from modules.slurm.job_registry import get_job

    status = check_job(job_id)
    accounting = None
    state, elapsed = parse_squeue_state_elapsed(status.get("output", ""))

    if not squeue_has_job_row(status.get("output", "")):
        accounting = check_job_accounting(job_id)

    remote_workdir = find_remote_job_dir(job_id)
    logs = tail_job_logs(job_id, remote_workdir, lines)
    combined_text = "\n".join([
        status.get("output", ""),
        status.get("error", ""),
        logs.get("output", ""),
        logs.get("error", ""),
    ])
    accounting_state = accounting.get("primary_state") if accounting else None
    accounting_elapsed = accounting.get("primary_elapsed") if accounting else None
    state = accounting_state or state
    elapsed = accounting_elapsed or elapsed
    is_completed = accounting_state == "COMPLETED"
    is_failed_terminal = accounting_state in TERMINAL_FAILURE_STATES
    failure_detected = is_failed_terminal

    if not accounting_state:
        log_failure_patterns = [
            "traceback",
            "segmentation fault",
            "out of memory",
            "oom-kill",
            "exception",
        ]
        failure_detected = any(
            pattern.lower() in combined_text.lower()
            for pattern in log_failure_patterns
        )

    vasp_diagnosis = None
    job_metadata = get_job(job_id) or {}
    remote_output_root = (VASP_REMOTE_OUTPUT_DIR or "").rstrip("/")
    remote_dir = (remote_workdir or "").rstrip("/")
    is_vasp_candidate = (
        job_metadata.get("type") == "vasp"
        or (
            bool(remote_output_root)
            and (
                remote_dir == remote_output_root
                or remote_dir.startswith(f"{remote_output_root}/")
            )
        )
    )

    if is_vasp_candidate:
        try:
            from modules.vasp.vasp_monitor import diagnose_remote_vasp_job

            vasp_diagnosis = diagnose_remote_vasp_job(
                remote_workdir=remote_workdir,
                log_output=logs.get("output", ""),
                log_error=logs.get("error", ""),
                run_remote_command=run_remote_command,
                job_is_terminal=is_completed or is_failed_terminal,
            )
            if vasp_diagnosis.get("severity") in {"error", "warning"}:
                failure_detected = True
        except Exception as error:
            vasp_diagnosis = {
                "is_vasp": False,
                "severity": "unknown",
                "summary": "VASP 诊断探测失败。",
                "issues": [],
                "evidence": [],
                "recommendations": [],
                "remote_files": [],
                "probe_error": f"{type(error).__name__}: {error}",
            }

    return {
        "job_id": str(job_id),
        "squeue_output": status.get("output", ""),
        "squeue_error": status.get("error", ""),
        "sacct_output": accounting.get("output", "") if accounting else "",
        "sacct_error": accounting.get("error", "") if accounting else "",
        "accounting_state": accounting_state,
        "state": state,
        "elapsed": elapsed,
        "is_completed": is_completed,
        "is_failed_terminal": is_failed_terminal,
        "remote_workdir": remote_workdir,
        "log_output": logs.get("output", ""),
        "log_error": logs.get("error", ""),
        "failure_detected": failure_detected,
        "vasp_diagnosis": vasp_diagnosis,
    }
