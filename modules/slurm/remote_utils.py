import re
import time
from pathlib import Path


def safe_remote_dir_name(name: str, default: str = "hpc_agent_job") -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe_name or default


def extract_job_name(script_text: str, default: str = "vasp_job") -> str:
    match = re.search(r"^#SBATCH\s+--job-name=([A-Za-z0-9_.-]+)\s*$", script_text, re.MULTILINE)
    if match:
        return match.group(1)

    return default


def make_remote_run_dir(root_dir: str, run_name: str, default: str = "hpc_agent_job") -> str:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    unique_suffix = f"{time.time_ns() % 1_000_000:06d}"
    safe_name = safe_remote_dir_name(run_name, default)
    return f"{root_dir}/{safe_name}_{timestamp}_{unique_suffix}"


def safe_upload_file_name(name: str) -> str:
    safe_name = Path(name).name
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", safe_name).strip("._")
    return safe_name or "uploaded_file"


def emit_progress(progress_callback, message: str):
    if progress_callback:
        progress_callback(message)
