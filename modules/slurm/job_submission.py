import re
import shlex
import time
from pathlib import Path

from modules.core.hpc_config import (
    REMOTE_WORKDIR,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
)
from modules.slurm.remote import create_remote_dir, get_ssh_client
from modules.slurm.remote_utils import (
    emit_progress,
    extract_job_name,
    make_remote_run_dir,
    safe_remote_dir_name,
    safe_upload_file_name,
)
from modules.slurm.vasp_sync import (
    local_vasp_output_dir_for_remote,
    local_vasp_raw_output_dir,
)


def add_vasp_input_sync(script_text: str, remote_input_dir: str) -> str:
    lines = script_text.splitlines()
    insert_index = 0

    if lines and lines[0].startswith("#!"):
        insert_index = 1

    while insert_index < len(lines) and lines[insert_index].startswith("#SBATCH"):
        insert_index += 1

    sync_lines = [
        "",
        "# Copy immutable VASP input files from the remote input directory into this output run directory.",
        f"VASP_INPUT_DIR={shlex.quote(remote_input_dir)}",
        "find \"$VASP_INPUT_DIR\" -mindepth 1 -maxdepth 1 ! -name job.sh -exec cp -R {} . \\;",
        "",
    ]
    return "\n".join(lines[:insert_index] + sync_lines + lines[insert_index:]) + "\n"


def submit_job(local_script_path, progress_callback=None):
    local_path = Path(local_script_path)
    script_text = local_path.read_text(encoding="utf-8", errors="replace")
    run_name = extract_job_name(script_text, local_path.stem)
    remote_run_dir = make_remote_run_dir(REMOTE_WORKDIR, run_name)

    client = get_ssh_client()

    emit_progress(progress_callback, "创建远程作业目录中...")
    mkdir_output, mkdir_error = create_remote_dir(client, remote_run_dir)

    if mkdir_error.strip():
        client.close()
        return {
            "success": False,
            "job_id": None,
            "remote_script": None,
            "remote_workdir": remote_run_dir,
            "output": mkdir_output,
            "error": mkdir_error,
        }

    sftp = client.open_sftp()
    remote_path = f"{remote_run_dir}/{local_path.name}"

    emit_progress(progress_callback, "上传脚本中...")
    sftp.put(str(local_path), remote_path)
    sftp.close()

    emit_progress(progress_callback, "提交作业中...")
    command = f"cd {shlex.quote(remote_run_dir)} && sbatch {shlex.quote(local_path.name)}"
    stdin, stdout, stderr = client.exec_command(command)
    output = stdout.read().decode()
    error = stderr.read().decode()
    client.close()

    match = re.search(r"Submitted batch job (\d+)", output)
    job_id = match.group(1) if match else None

    if error.strip() == "" and job_id:
        from modules.slurm.job_registry import register_job

        register_job(
            job_id,
            {
                "type": "slurm",
                "job_id": job_id,
                "remote_workdir": remote_run_dir,
                "remote_script": remote_path,
            },
        )

    return {
        "success": error.strip() == "",
        "job_id": job_id,
        "remote_script": remote_path,
        "remote_workdir": remote_run_dir,
        "output": output,
        "error": error,
    }


def submit_script_text(script_text, script_name=None, uploaded_files=None, progress_callback=None):
    if script_name is None:
        script_name = "job.sh"

    run_name = extract_job_name(script_text, "hpc_agent_job")
    remote_run_dir = make_remote_run_dir(REMOTE_WORKDIR, run_name)
    uploaded_files = uploaded_files or []

    client = get_ssh_client()

    emit_progress(progress_callback, "创建远程作业目录中...")
    mkdir_output, mkdir_error = create_remote_dir(client, remote_run_dir)

    if mkdir_error.strip():
        client.close()
        return {
            "success": False,
            "job_id": None,
            "remote_script": None,
            "remote_workdir": remote_run_dir,
            "output": mkdir_output,
            "error": mkdir_error,
        }

    sftp = client.open_sftp()
    remote_path = f"{remote_run_dir}/{script_name}"

    emit_progress(progress_callback, "上传脚本中...")
    with sftp.open(remote_path, "w") as remote_file:
        remote_file.write(script_text)

    remote_uploaded_files = [remote_path]

    for upload in uploaded_files:
        file_name = safe_upload_file_name(upload["name"])
        remote_file_path = f"{remote_run_dir}/{file_name}"

        emit_progress(progress_callback, f"上传附件中: {file_name}")
        with sftp.open(remote_file_path, "wb") as remote_file:
            remote_file.write(upload["content"])
        remote_uploaded_files.append(remote_file_path)

    sftp.close()

    emit_progress(progress_callback, "提交作业中...")
    command = f"cd {shlex.quote(remote_run_dir)} && sbatch {shlex.quote(script_name)}"
    stdin, stdout, stderr = client.exec_command(command)
    output = stdout.read().decode()
    error = stderr.read().decode()
    client.close()

    match = re.search(r"Submitted batch job (\d+)", output)
    job_id = match.group(1) if match else None

    if error.strip() == "" and job_id:
        from modules.slurm.job_registry import register_job

        register_job(
            job_id,
            {
                "type": "slurm",
                "job_id": job_id,
                "remote_workdir": remote_run_dir,
                "remote_script": remote_path,
                "uploaded_files": remote_uploaded_files,
            },
        )

    return {
        "success": error.strip() == "",
        "job_id": job_id,
        "remote_script": remote_path,
        "remote_workdir": remote_run_dir,
        "uploaded_files": remote_uploaded_files,
        "output": output,
        "error": error,
    }


def submit_vasp_script_text(script_text, local_input_dir=None, run_name=None, progress_callback=None):
    if local_input_dir is None:
        local_input_dir = "."

    input_dir = Path(local_input_dir)
    input_files = ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]
    required_paths = [input_dir / name for name in input_files]

    missing_files = [
        path.name
        for path in required_paths
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

    local_paths = [
        path
        for path in sorted(input_dir.iterdir())
        if path.is_file()
    ]

    if run_name is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        job_name = safe_remote_dir_name(extract_job_name(script_text))
        run_name = f"{job_name}_{timestamp}"
    else:
        run_name = safe_remote_dir_name(run_name)

    remote_input_dir = f"{VASP_REMOTE_INPUT_DIR}/{run_name}"
    remote_output_dir = f"{VASP_REMOTE_OUTPUT_DIR}/{run_name}"
    remote_script = f"{remote_output_dir}/job.sh"
    local_output_dir = local_vasp_output_dir_for_remote(remote_output_dir)
    local_raw_output_dir = local_vasp_raw_output_dir(local_output_dir)
    local_analysis_dir = local_output_dir / "analysis"
    runnable_script_text = add_vasp_input_sync(script_text, remote_input_dir)

    client = get_ssh_client()

    try:
        emit_progress(progress_callback, "创建远程 VASP 输入/输出目录中...")
        mkdir_command = f"mkdir -p {shlex.quote(remote_input_dir)} {shlex.quote(remote_output_dir)}"
        stdin, stdout, stderr = client.exec_command(mkdir_command)
        mkdir_output = stdout.read().decode()
        mkdir_error = stderr.read().decode()

        if mkdir_error.strip():
            return {
                "success": False,
                "job_id": None,
                "remote_script": remote_script,
                "remote_workdir": remote_output_dir,
                "remote_input_dir": remote_input_dir,
                "remote_output_dir": remote_output_dir,
                "uploaded_files": [],
                "output": mkdir_output,
                "error": mkdir_error,
            }

        sftp = client.open_sftp()
        uploaded_files = []

        try:
            emit_progress(progress_callback, "上传 VASP 输入文件中...")
            for local_path in local_paths:
                remote_path = f"{remote_input_dir}/{local_path.name}"
                sftp.put(str(local_path), remote_path)
                uploaded_files.append(remote_path)

            emit_progress(progress_callback, "上传 VASP 作业脚本中...")
            with sftp.open(remote_script, "w") as remote_file:
                remote_file.write(runnable_script_text)
            uploaded_files.append(remote_script)
        finally:
            sftp.close()
    finally:
        client.close()

    emit_progress(progress_callback, "提交 VASP 作业中...")
    command = f"cd {shlex.quote(remote_output_dir)} && sbatch job.sh"
    submit_client = get_ssh_client()

    try:
        stdin, stdout, stderr = submit_client.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()
    finally:
        submit_client.close()

    match = re.search(r"Submitted batch job (\d+)", output)
    job_id = match.group(1) if match else None

    return {
        "success": error.strip() == "",
        "job_id": job_id,
        "remote_script": remote_script,
        "remote_workdir": remote_output_dir,
        "remote_input_dir": remote_input_dir,
        "remote_output_dir": remote_output_dir,
        "local_output_dir": str(local_output_dir),
        "local_raw_output_dir": str(local_raw_output_dir),
        "local_analysis_dir": str(local_analysis_dir),
        "uploaded_files": uploaded_files,
        "output": output,
        "error": error,
    }
