import re
import time
import os
import shlex
from pathlib import Path

import paramiko
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = os.getenv("HPC_HOST")
USERNAME = os.getenv("HPC_USERNAME")
KEY_PATH = os.getenv("HPC_KEY_PATH")
REMOTE_WORKDIR = os.getenv("HPC_REMOTE_WORKDIR")
VASP_REMOTE_WORKDIR = os.getenv("HPC_VASP_REMOTE_WORKDIR", REMOTE_WORKDIR)


def get_ssh_client():
    client = paramiko.SSHClient()

    client.set_missing_host_key_policy(
        paramiko.AutoAddPolicy()
    )

    key = paramiko.Ed25519Key.from_private_key_file(
        KEY_PATH
    )

    client.connect(
        hostname=HOST,
        username=USERNAME,
        pkey=key,
    )

    return client


def run_remote_command(command):
    client = get_ssh_client()

    stdin, stdout, stderr = client.exec_command(command)

    output = stdout.read().decode()
    error = stderr.read().decode()

    client.close()

    return output, error


def submit_job(local_script_path):
    local_path = Path(local_script_path)

    client = get_ssh_client()
    sftp = client.open_sftp()

    remote_path = f"{REMOTE_WORKDIR}/{local_path.name}"

    print("上传脚本中...")
    sftp.put(str(local_path), remote_path)
    sftp.close()

    print("提交作业中...")
    command = f"cd {REMOTE_WORKDIR} && sbatch {local_path.name}"

    stdin, stdout, stderr = client.exec_command(command)

    output = stdout.read().decode()
    error = stderr.read().decode()

    client.close()

    match = re.search(r"Submitted batch job (\d+)", output)
    job_id = match.group(1) if match else None

    return {
        "success": error.strip() == "",
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def submit_script_text(script_text, script_name=None):
    if script_name is None:
        script_name = f"hpc_agent_{int(time.time())}.sh"

    client = get_ssh_client()
    sftp = client.open_sftp()

    remote_path = f"{REMOTE_WORKDIR}/{script_name}"

    print("上传脚本中...")
    with sftp.open(remote_path, "w") as remote_file:
        remote_file.write(script_text)

    sftp.close()

    print("提交作业中...")
    command = f"cd {REMOTE_WORKDIR} && sbatch {script_name}"

    stdin, stdout, stderr = client.exec_command(command)

    output = stdout.read().decode()
    error = stderr.read().decode()

    client.close()

    match = re.search(r"Submitted batch job (\d+)", output)
    job_id = match.group(1) if match else None

    return {
        "success": error.strip() == "",
        "job_id": job_id,
        "remote_script": remote_path,
        "output": output,
        "error": error,
    }


def _extract_job_name(script_text: str, default: str = "vasp_job") -> str:
    match = re.search(r"^#SBATCH\s+--job-name=([A-Za-z0-9_.-]+)\s*$", script_text, re.MULTILINE)
    if match:
        return match.group(1)

    return default


def _safe_remote_dir_name(name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe_name or "vasp_job"


def submit_vasp_script_text(script_text, local_input_dir=None, run_name=None):
    if local_input_dir is None:
        local_input_dir = "."

    input_dir = Path(local_input_dir)
    input_files = ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]
    local_paths = [input_dir / name for name in input_files]

    missing_files = [
        path.name
        for path in local_paths
        if not path.is_file()
    ]

    if missing_files:
        return {
            "success": False,
            "job_id": None,
            "remote_script": None,
            "remote_workdir": None,
            "uploaded_files": [],
            "output": "",
            "error": (
                "本地 VASP 输入文件不完整，未提交作业。缺少: "
                + ", ".join(missing_files)
            ),
        }

    if run_name is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        job_name = _safe_remote_dir_name(_extract_job_name(script_text))
        run_name = f"{job_name}_{timestamp}"
    else:
        run_name = _safe_remote_dir_name(run_name)

    remote_run_dir = f"{VASP_REMOTE_WORKDIR}/{run_name}"
    remote_script = f"{remote_run_dir}/job.sh"

    client = get_ssh_client()

    print("创建远程 VASP 作业目录中...")
    mkdir_command = f"mkdir -p {shlex.quote(remote_run_dir)}"
    stdin, stdout, stderr = client.exec_command(mkdir_command)
    mkdir_output = stdout.read().decode()
    mkdir_error = stderr.read().decode()

    if mkdir_error.strip():
        client.close()
        return {
            "success": False,
            "job_id": None,
            "remote_script": remote_script,
            "remote_workdir": remote_run_dir,
            "uploaded_files": [],
            "output": mkdir_output,
            "error": mkdir_error,
        }

    sftp = client.open_sftp()
    uploaded_files = []

    print("上传 VASP 输入文件中...")
    for local_path in local_paths:
        remote_path = f"{remote_run_dir}/{local_path.name}"
        sftp.put(str(local_path), remote_path)
        uploaded_files.append(remote_path)

    print("上传 VASP 作业脚本中...")
    with sftp.open(remote_script, "w") as remote_file:
        remote_file.write(script_text)
    uploaded_files.append(remote_script)

    sftp.close()

    print("提交 VASP 作业中...")
    command = f"cd {shlex.quote(remote_run_dir)} && sbatch job.sh"

    stdin, stdout, stderr = client.exec_command(command)

    output = stdout.read().decode()
    error = stderr.read().decode()

    client.close()

    match = re.search(r"Submitted batch job (\d+)", output)
    job_id = match.group(1) if match else None

    return {
        "success": error.strip() == "",
        "job_id": job_id,
        "remote_script": remote_script,
        "remote_workdir": remote_run_dir,
        "uploaded_files": uploaded_files,
        "output": output,
        "error": error,
    }


def check_job(job_id):
    command = f"squeue -j {job_id}"

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def read_job_output(job_id):
    from modules.job_registry import get_job

    job = get_job(job_id)

    if job and job.get("type") == "vasp" and job.get("remote_workdir"):
        remote_dir = shlex.quote(job["remote_workdir"])
        command = (
            f"cd {remote_dir} && "
            "{ "
            "echo 'Remote VASP directory:'; pwd; "
            "echo ''; echo 'Files:'; ls -1; "
            "echo ''; echo 'vasp.out:'; "
            "if [ -f vasp.out ]; then cat vasp.out; "
            f"elif ls *_{job_id}.out >/dev/null 2>&1; then cat *_{job_id}.out; "
            "elif ls *.out >/dev/null 2>&1; then cat *.out; "
            "else echo 'No VASP stdout file found yet.'; fi; "
            "}"
        )

        output, error = run_remote_command(command)

        return {
            "job_id": job_id,
            "output": output,
            "error": error,
        }

    command = (
        f"cd {REMOTE_WORKDIR} && "
        f"cat hpc_agent_job_{job_id}.out 2>/dev/null || "
        f"cat agent_{job_id}.out"
    )

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def read_job_error(job_id):
    from modules.job_registry import get_job

    job = get_job(job_id)

    if job and job.get("type") == "vasp" and job.get("remote_workdir"):
        remote_dir = shlex.quote(job["remote_workdir"])
        command = (
            f"cd {remote_dir} && "
            "{ "
            "echo 'Remote VASP directory:'; pwd; "
            "echo ''; echo 'Files:'; ls -1; "
            "echo ''; echo 'Slurm/VASP stderr:'; "
            f"if ls *_{job_id}.err >/dev/null 2>&1; then cat *_{job_id}.err; "
            "elif ls *.err >/dev/null 2>&1; then cat *.err; "
            "else echo 'No VASP stderr file found yet.'; fi; "
            "}"
        )

        output, error = run_remote_command(command)

        return {
            "job_id": job_id,
            "output": output,
            "error": error,
        }

    command = (
        f"cd {REMOTE_WORKDIR} && "
        f"cat hpc_agent_job_{job_id}.err 2>/dev/null || "
        f"cat agent_{job_id}.err"
    )

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def cancel_job(job_id):
    command = f"scancel {job_id}"

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }
