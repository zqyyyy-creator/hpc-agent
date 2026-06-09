import re
import time
import os
from pathlib import Path

import paramiko
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = os.getenv("HPC_HOST", "ssh.cn-zhongwei-1.paracloud.com")
USERNAME = os.getenv("HPC_USERNAME", "a0s000582@BSCC-A")
KEY_PATH = os.getenv("HPC_KEY_PATH", "/home/lenovo/.ssh/id_ed25519")
REMOTE_WORKDIR = os.getenv("HPC_REMOTE_WORKDIR", "/public4/home/a0s000582")


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


def check_job(job_id):
    command = f"squeue -j {job_id}"

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def read_job_output(job_id):
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
