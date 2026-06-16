import fnmatch
import json
import re
import time
import shlex
import stat
from pathlib import Path

import paramiko
from modules.core.hpc_config import (
    HOST,
    KEY_PATH,
    REMOTE_WORKDIR,
    USERNAME,
    VASP_LOCAL_OUTPUT_DIR,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
    VASP_REMOTE_WORKDIR,
)
VASP_SYNC_INCLUDE_PATTERNS = [
    "INCAR",
    "POSCAR",
    "KPOINTS",
    "OUTCAR",
    "OSZICAR",
    "CONTCAR",
    "XDATCAR",
    "vasprun.xml",
    "vasp.out",
    "job.sh",
    "*.out",
    "*.err",
]
VASP_SYNC_EXCLUDE_PATTERNS = [
    "WAVECAR",
    "CHGCAR",
    "AECCAR*",
    "POTCAR",
]


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


def _safe_remote_dir_name(name: str, default: str = "hpc_agent_job") -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe_name or default


def _extract_job_name(script_text: str, default: str = "vasp_job") -> str:
    match = re.search(r"^#SBATCH\s+--job-name=([A-Za-z0-9_.-]+)\s*$", script_text, re.MULTILINE)
    if match:
        return match.group(1)

    return default


def _make_remote_run_dir(root_dir: str, run_name: str, default: str = "hpc_agent_job") -> str:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    unique_suffix = f"{time.time_ns() % 1_000_000:06d}"
    safe_name = _safe_remote_dir_name(run_name, default)
    return f"{root_dir}/{safe_name}_{timestamp}_{unique_suffix}"


def _local_vasp_output_dir_for_remote(remote_output_dir: str) -> Path:
    run_name = Path(remote_output_dir).name
    return Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / run_name


def _resolve_vasp_local_output_dir(
    remote_output_dir: str,
    preferred_local_output_dir: str | Path | None = None,
) -> Path:
    canonical = _local_vasp_output_dir_for_remote(remote_output_dir)

    if not preferred_local_output_dir:
        return canonical

    preferred = Path(preferred_local_output_dir).expanduser()
    output_root = Path(VASP_LOCAL_OUTPUT_DIR).expanduser()

    try:
        preferred.resolve().relative_to(output_root.resolve())
        if preferred.resolve() == canonical.resolve():
            return preferred
    except ValueError:
        pass

    return canonical


def _local_vasp_raw_output_dir(local_job_dir: Path) -> Path:
    return local_job_dir / "raw_output"


def _should_sync_vasp_output_file(file_name: str) -> bool:
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in VASP_SYNC_EXCLUDE_PATTERNS):
        return False

    return any(fnmatch.fnmatch(file_name, pattern) for pattern in VASP_SYNC_INCLUDE_PATTERNS)


def _sftp_file_size(attr) -> int:
    return int(getattr(attr, "st_size", 0) or 0)


def _write_vasp_file_manifest(local_job_dir: Path, files: list[dict]) -> Path:
    analysis_dir = local_job_dir / "analysis"
    raw_output_dir = _local_vasp_raw_output_dir(local_job_dir)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = analysis_dir / "file_manifest.json"
    manifest = {
        "local_job_dir": str(local_job_dir),
        "raw_output_dir": str(raw_output_dir),
        "analysis_dir": str(analysis_dir),
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _has_meaningful_vasp_synced_files(files: list[dict]) -> bool:
    meaningful_names = {
        "INCAR",
        "POSCAR",
        "KPOINTS",
        "OUTCAR",
        "OSZICAR",
        "CONTCAR",
        "XDATCAR",
        "vasprun.xml",
        "vasp.out",
    }

    for item in files:
        name = item.get("name", "")
        if name in meaningful_names or name.endswith(".out") or name.endswith(".err"):
            return True

    return False


def sync_vasp_output_to_local(
    remote_output_dir: str,
    local_output_dir: str | Path = None,
    progress_callback=None,
):
    local_job_dir = Path(local_output_dir).expanduser() if local_output_dir else _local_vasp_output_dir_for_remote(remote_output_dir)
    local_raw_output_dir = _local_vasp_raw_output_dir(local_job_dir)
    local_job_dir.mkdir(parents=True, exist_ok=True)
    local_raw_output_dir.mkdir(parents=True, exist_ok=True)
    (local_job_dir / "analysis").mkdir(parents=True, exist_ok=True)

    client = get_ssh_client()
    sftp = client.open_sftp()
    synced_files = []
    skipped_files = []

    try:
        _emit_progress(progress_callback, "扫描远端 VASP 输出目录中...")
        try:
            remote_attrs = sftp.listdir_attr(remote_output_dir)
        except FileNotFoundError as error:
            return {
                "success": False,
                "remote_output_dir": remote_output_dir,
                "local_output_dir": str(local_job_dir),
                "local_raw_output_dir": str(local_raw_output_dir),
                "local_analysis_dir": str(local_job_dir / "analysis"),
                "manifest_path": None,
                "synced_files": [],
                "skipped_files": [],
                "error": f"远端 VASP 输出目录不存在: {remote_output_dir}. Details: {error}",
            }

        for attr in remote_attrs:
            file_name = attr.filename
            remote_path = f"{remote_output_dir}/{file_name}"

            if attr.st_mode is not None and not stat.S_ISREG(attr.st_mode):
                skipped_files.append({
                    "name": file_name,
                    "reason": "not_regular_file",
                    "size_bytes": _sftp_file_size(attr),
                })
                continue

            if not _should_sync_vasp_output_file(file_name):
                skipped_files.append({
                    "name": file_name,
                    "reason": "not_in_sync_whitelist_or_excluded",
                    "size_bytes": _sftp_file_size(attr),
                })
                continue

            local_path = local_raw_output_dir / file_name
            _emit_progress(progress_callback, f"同步 VASP 输出文件: {file_name}")
            sftp.get(remote_path, str(local_path))
            synced_files.append({
                "name": file_name,
                "remote_path": remote_path,
                "local_path": str(local_path),
                "size_bytes": _sftp_file_size(attr),
            })
    finally:
        sftp.close()
        client.close()

    if not _has_meaningful_vasp_synced_files(synced_files):
        return {
            "success": False,
            "remote_output_dir": remote_output_dir,
            "local_output_dir": str(local_job_dir),
            "local_raw_output_dir": str(local_raw_output_dir),
            "local_analysis_dir": str(local_job_dir / "analysis"),
            "manifest_path": None,
            "synced_files": synced_files,
            "skipped_files": skipped_files,
            "error": (
                "远端 VASP 输出目录当前没有可同步的有效文件。"
                " 这通常表示作业还没有开始写出结果，或远端输出目录不正确。"
            ),
        }

    manifest_path = _write_vasp_file_manifest(local_job_dir, synced_files)
    report_context_path = None
    report_context_error = None

    try:
        from modules.vasp.vasp_report_context import generate_vasp_report_context

        context_result = generate_vasp_report_context(local_job_dir)
        report_context_path = context_result["report_context_path"]
    except Exception as error:
        report_context_error = f"{type(error).__name__}: {error}"

    result = {
        "success": True,
        "remote_output_dir": remote_output_dir,
        "local_output_dir": str(local_job_dir),
        "local_raw_output_dir": str(local_raw_output_dir),
        "local_analysis_dir": str(local_job_dir / "analysis"),
        "manifest_path": str(manifest_path),
        "synced_files": synced_files,
        "skipped_files": skipped_files,
    }

    if report_context_path:
        result["report_context_path"] = report_context_path
    if report_context_error:
        result["report_context_error"] = report_context_error

    return result


def sync_vasp_job_output(job_id: str, progress_callback=None):
    from modules.slurm.job_registry import get_job, register_job

    job = get_job(job_id)

    if not job:
        return {
            "success": False,
            "job_id": str(job_id),
            "remote_output_dir": None,
            "local_output_dir": None,
            "error": "本地 registry 中没有找到该 VASP 作业，请先提交或登记这个 Job ID。",
        }

    if job.get("type") != "vasp":
        return {
            "success": False,
            "job_id": str(job_id),
            "remote_output_dir": job.get("remote_workdir"),
            "local_output_dir": None,
            "error": "该 Job ID 不是 VASP 作业。",
        }

    remote_output_dir = job.get("remote_output_dir") or job.get("remote_workdir")

    if not remote_output_dir:
        return {
            "success": False,
            "job_id": str(job_id),
            "remote_output_dir": None,
            "local_output_dir": None,
            "error": "该 VASP 作业没有登记远端输出目录。",
        }

    local_output_dir = _resolve_vasp_local_output_dir(
        remote_output_dir,
        job.get("local_output_dir"),
    )
    result = sync_vasp_output_to_local(
        remote_output_dir,
        local_output_dir=local_output_dir,
        progress_callback=progress_callback,
    )
    result["job_id"] = str(job_id)

    updated_job = dict(job)
    updated_job["local_output_dir"] = result["local_output_dir"]
    updated_job["local_raw_output_dir"] = result["local_raw_output_dir"]
    updated_job["local_analysis_dir"] = result["local_analysis_dir"]
    updated_job["file_manifest"] = result["manifest_path"]

    try:
        from modules.vasp.vasp_report_context import generate_vasp_report_context

        context_result = generate_vasp_report_context(result["local_output_dir"])
        result["report_context_path"] = context_result["report_context_path"]
        updated_job["report_context"] = context_result["report_context_path"]
    except Exception as error:
        result["report_context_error"] = f"{type(error).__name__}: {error}"

    register_job(str(job_id), updated_job)

    return result


def _create_remote_dir(client, remote_dir: str):
    command = f"mkdir -p {shlex.quote(remote_dir)}"
    stdin, stdout, stderr = client.exec_command(command)

    return stdout.read().decode(), stderr.read().decode()


def _safe_upload_file_name(name: str) -> str:
    safe_name = Path(name).name
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", safe_name).strip("._")
    return safe_name or "uploaded_file"


def _emit_progress(progress_callback, message: str):
    if progress_callback:
        progress_callback(message)


def _add_vasp_input_sync(script_text: str, remote_input_dir: str) -> str:
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
    run_name = _extract_job_name(script_text, local_path.stem)
    remote_run_dir = _make_remote_run_dir(REMOTE_WORKDIR, run_name)

    client = get_ssh_client()

    _emit_progress(progress_callback, "创建远程作业目录中...")
    mkdir_output, mkdir_error = _create_remote_dir(client, remote_run_dir)

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

    _emit_progress(progress_callback, "上传脚本中...")
    sftp.put(str(local_path), remote_path)
    sftp.close()

    _emit_progress(progress_callback, "提交作业中...")
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

    run_name = _extract_job_name(script_text, "hpc_agent_job")
    remote_run_dir = _make_remote_run_dir(REMOTE_WORKDIR, run_name)
    uploaded_files = uploaded_files or []

    client = get_ssh_client()

    _emit_progress(progress_callback, "创建远程作业目录中...")
    mkdir_output, mkdir_error = _create_remote_dir(client, remote_run_dir)

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

    _emit_progress(progress_callback, "上传脚本中...")
    with sftp.open(remote_path, "w") as remote_file:
        remote_file.write(script_text)

    remote_uploaded_files = [remote_path]

    for upload in uploaded_files:
        file_name = _safe_upload_file_name(upload["name"])
        remote_file_path = f"{remote_run_dir}/{file_name}"

        _emit_progress(progress_callback, f"上传附件中: {file_name}")
        with sftp.open(remote_file_path, "wb") as remote_file:
            remote_file.write(upload["content"])
        remote_uploaded_files.append(remote_file_path)

    sftp.close()

    _emit_progress(progress_callback, "提交作业中...")
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
        job_name = _safe_remote_dir_name(_extract_job_name(script_text))
        run_name = f"{job_name}_{timestamp}"
    else:
        run_name = _safe_remote_dir_name(run_name)

    remote_input_dir = f"{VASP_REMOTE_INPUT_DIR}/{run_name}"
    remote_output_dir = f"{VASP_REMOTE_OUTPUT_DIR}/{run_name}"
    remote_script = f"{remote_output_dir}/job.sh"
    local_output_dir = _local_vasp_output_dir_for_remote(remote_output_dir)
    local_raw_output_dir = _local_vasp_raw_output_dir(local_output_dir)
    local_analysis_dir = local_output_dir / "analysis"
    runnable_script_text = _add_vasp_input_sync(script_text, remote_input_dir)

    client = get_ssh_client()

    try:
        _emit_progress(progress_callback, "创建远程 VASP 输入/输出目录中...")
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
            _emit_progress(progress_callback, "上传 VASP 输入文件中...")
            for local_path in local_paths:
                remote_path = f"{remote_input_dir}/{local_path.name}"
                sftp.put(str(local_path), remote_path)
                uploaded_files.append(remote_path)

            _emit_progress(progress_callback, "上传 VASP 作业脚本中...")
            with sftp.open(remote_script, "w") as remote_file:
                remote_file.write(runnable_script_text)
            uploaded_files.append(remote_script)
        finally:
            sftp.close()
    finally:
        client.close()

    _emit_progress(progress_callback, "提交 VASP 作业中...")
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


def _parse_squeue_state_elapsed(output: str):
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


def _squeue_has_job_row(output: str) -> bool:
    return len([line for line in output.splitlines() if line.strip()]) >= 2


def validate_monitorable_job(job_id):
    status = check_job(job_id)
    state, elapsed = _parse_squeue_state_elapsed(status.get("output", ""))

    if _squeue_has_job_row(status.get("output", "")):
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


def _find_remote_job_dir(job_id: str):
    from modules.slurm.job_registry import get_job

    job = get_job(job_id)

    if job and job.get("remote_workdir"):
        return job["remote_workdir"]

    for root_dir in [REMOTE_WORKDIR, VASP_REMOTE_OUTPUT_DIR]:
        found_dir = _find_remote_job_dir_under_root(job_id, root_dir)

        if found_dir:
            return found_dir

    return None


def _find_remote_job_dir_under_root(job_id: str, root_dir: str):
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
    remote_workdir = remote_workdir or _find_remote_job_dir(job_id)

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
    state, elapsed = _parse_squeue_state_elapsed(status.get("output", ""))

    if not _squeue_has_job_row(status.get("output", "")):
        accounting = check_job_accounting(job_id)

    remote_workdir = _find_remote_job_dir(job_id)
    logs = tail_job_logs(job_id, remote_workdir, lines)
    combined_text = "\n".join([
        status.get("output", ""),
        status.get("error", ""),
        logs.get("output", ""),
        logs.get("error", ""),
    ])
    terminal_failure_states = {
        "FAILED",
        "CANCELLED",
        "TIMEOUT",
        "OUT_OF_MEMORY",
        "NODE_FAIL",
        "PREEMPTED",
        "BOOT_FAIL",
    }
    accounting_state = accounting.get("primary_state") if accounting else None
    accounting_elapsed = accounting.get("primary_elapsed") if accounting else None
    state = accounting_state or state
    elapsed = accounting_elapsed or elapsed
    is_completed = accounting_state == "COMPLETED"
    is_failed_terminal = accounting_state in terminal_failure_states
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


def list_remote_agent_jobs():
    command = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        "find . -maxdepth 3 -type f "
        "\\( -name '*.out' -o -name '*.err' -o -name 'job.sh' \\) "
        "-printf '%P\\n' | sort"
    )

    output, error = run_remote_command(command)

    return {
        "remote_workdir": REMOTE_WORKDIR,
        "output": output,
        "error": error,
    }


def list_remote_vasp_jobs():
    roots = [
        ("input", VASP_REMOTE_INPUT_DIR),
        ("output", VASP_REMOTE_OUTPUT_DIR),
    ]
    outputs = []
    errors = []

    for label, root_dir in roots:
        if not root_dir:
            errors.append(f"{label}: 未配置远端 VASP {label} 目录。")
            continue

        command = (
            f"cd {shlex.quote(root_dir)} && "
            "find . -mindepth 1 -maxdepth 1 "
            "-printf '%y\\t%P\\n' | sort"
        )
        output, error = run_remote_command(command)
        outputs.append(f"## {label}\nroot\t{root_dir}\n{output.rstrip()}")

        if error.strip():
            errors.append(f"{label}: {error.rstrip()}")

    return {
        "remote_input_dir": VASP_REMOTE_INPUT_DIR,
        "remote_output_dir": VASP_REMOTE_OUTPUT_DIR,
        "output": "\n\n".join(outputs).strip(),
        "error": "\n".join(errors),
    }


def _is_safe_remote_cleanup_target(path: str) -> bool:
    if not path or path.startswith("/") or path.startswith("-"):
        return False

    parts = Path(path).parts
    return ".." not in parts and "." not in parts


def _parse_cleanup_targets(output: str):
    targets = []
    seen = set()

    for line in output.splitlines():
        parts = line.strip().split("\t", 1)

        if len(parts) != 2:
            continue

        kind, path = parts
        path = path.strip().lstrip("./")

        if kind not in {"DIR", "FILE"}:
            continue

        if not _is_safe_remote_cleanup_target(path):
            continue

        key = (kind, path)

        if key in seen:
            continue

        seen.add(key)
        targets.append({
            "kind": kind.lower(),
            "path": path,
        })

    return targets


def find_remote_agent_job_cleanup_targets(job_id: str):
    if not re.fullmatch(r"\d{4,}", str(job_id)):
        return {
            "success": False,
            "remote_workdir": REMOTE_WORKDIR,
            "targets": [],
            "output": "",
            "error": "Job ID 格式无效。",
        }

    safe_job_id = shlex.quote(str(job_id))
    command = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        "{ "
        "find . -mindepth 2 -maxdepth 3 -type f "
        f"\\( -name '*_{safe_job_id}.out' -o -name '*_{safe_job_id}.err' \\) "
        "-printf 'DIR\\t%h\\n'; "
        "find . -maxdepth 1 -type f "
        f"\\( -name '*_{safe_job_id}.out' -o -name '*_{safe_job_id}.err' \\) "
        "-printf 'FILE\\t%P\\n'; "
        "} | sort -u"
    )

    output, error = run_remote_command(command)

    return {
        "success": error.strip() == "",
        "remote_workdir": REMOTE_WORKDIR,
        "targets": [
            {**target, "remote_workdir": REMOTE_WORKDIR}
            for target in _parse_cleanup_targets(output)
        ],
        "output": output,
        "error": error,
    }


def find_all_remote_agent_cleanup_targets():
    command = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        "find . -mindepth 1 -maxdepth 1 "
        "-printf '%y\\t%P\\n' | sort"
    )

    output, error = run_remote_command(command)
    targets = []
    seen = set()

    for line in output.splitlines():
        parts = line.strip().split("\t", 1)

        if len(parts) != 2:
            continue

        file_type, path = parts

        if file_type not in {"d", "f"}:
            continue

        if not _is_safe_remote_cleanup_target(path):
            continue

        kind = "dir" if file_type == "d" else "file"
        key = (kind, path)

        if key in seen:
            continue

        seen.add(key)
        targets.append({
            "kind": kind,
            "path": path,
            "remote_workdir": REMOTE_WORKDIR,
        })

    return {
        "success": error.strip() == "",
        "remote_workdir": REMOTE_WORKDIR,
        "targets": targets,
        "output": output,
        "error": error,
    }


def _vasp_cleanup_roots(scope: str = "both"):
    normalized = (scope or "both").lower()
    roots = []

    if normalized in {"input", "both", "all"} and VASP_REMOTE_INPUT_DIR:
        roots.append(("input", VASP_REMOTE_INPUT_DIR))

    if normalized in {"output", "both", "all"} and VASP_REMOTE_OUTPUT_DIR:
        roots.append(("output", VASP_REMOTE_OUTPUT_DIR))

    return roots


def _target_for_remote_vasp_dir(root_dir: str, remote_dir: str, label: str):
    root = root_dir.rstrip("/")
    directory = remote_dir.rstrip("/")

    if directory == root:
        return None

    if not directory.startswith(f"{root}/"):
        return None

    relative_path = directory[len(root) + 1:]

    if not _is_safe_remote_cleanup_target(relative_path):
        return None

    return {
        "kind": "dir",
        "path": relative_path,
        "remote_workdir": root_dir,
        "scope": label,
    }


def find_remote_vasp_job_cleanup_targets(selector: str, scope: str = "both"):
    from modules.slurm.job_registry import get_job

    selector = str(selector).strip()
    targets = []
    errors = []
    outputs = []
    roots = _vasp_cleanup_roots(scope)

    if not roots:
        return {
            "success": False,
            "remote_workdir": None,
            "remote_workdirs": [],
            "targets": [],
            "output": "",
            "error": "未配置可用的远端 VASP input/output 目录。",
        }

    if re.fullmatch(r"\d{4,}", selector):
        job = get_job(selector) or {}

        if job.get("type") == "vasp":
            registry_paths = {
                "input": job.get("remote_input_dir"),
                "output": job.get("remote_output_dir") or job.get("remote_workdir"),
            }
            for label, root_dir in roots:
                target = _target_for_remote_vasp_dir(root_dir, registry_paths.get(label, ""), label)
                if target:
                    targets.append(target)

        safe_selector = shlex.quote(selector)
        for label, root_dir in roots:
            command = (
                f"cd {shlex.quote(root_dir)} && "
                "{ "
                "find . -mindepth 2 -maxdepth 3 -type f "
                f"\\( -name '*_{safe_selector}.out' -o -name '*_{safe_selector}.err' \\) "
                "-printf 'DIR\\t%h\\n'; "
                "find . -maxdepth 1 -type d "
                f"-name '*{safe_selector}*' -printf 'DIR\\t%P\\n'; "
                "} | sort -u"
            )
            output, error = run_remote_command(command)
            outputs.append(f"## {label}\n{output.rstrip()}")
            if error.strip():
                errors.append(f"{label}: {error.rstrip()}")
            for target in _parse_cleanup_targets(output):
                targets.append({
                    **target,
                    "remote_workdir": root_dir,
                    "scope": label,
                })
    else:
        safe_name = _safe_remote_dir_name(selector)
        if not safe_name:
            return {
                "success": False,
                "remote_workdir": None,
                "remote_workdirs": [root for _, root in roots],
                "targets": [],
                "output": "",
                "error": "VASP 作业名格式无效。",
            }

        for label, root_dir in roots:
            command = (
                f"cd {shlex.quote(root_dir)} && "
                "find . -maxdepth 1 -type d "
                f"\\( -name {shlex.quote(safe_name)} -o -name {shlex.quote(f'*{safe_name}*')} \\) "
                "-printf 'DIR\\t%P\\n' | sort -u"
            )
            output, error = run_remote_command(command)
            outputs.append(f"## {label}\n{output.rstrip()}")
            if error.strip():
                errors.append(f"{label}: {error.rstrip()}")
            for target in _parse_cleanup_targets(output):
                targets.append({
                    **target,
                    "remote_workdir": root_dir,
                    "scope": label,
                })

    deduped = []
    seen = set()
    for target in targets:
        key = (target["remote_workdir"], target["kind"], target["path"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)

    return {
        "success": not errors,
        "remote_workdir": None,
        "remote_workdirs": [root for _, root in roots],
        "targets": deduped,
        "output": "\n\n".join(outputs),
        "error": "\n".join(errors),
    }


def find_all_remote_vasp_cleanup_targets(scope: str = "both"):
    roots = _vasp_cleanup_roots(scope)
    targets = []
    outputs = []
    errors = []

    if not roots:
        return {
            "success": False,
            "remote_workdir": None,
            "remote_workdirs": [],
            "targets": [],
            "output": "",
            "error": "未配置可用的远端 VASP input/output 目录。",
        }

    for label, root_dir in roots:
        command = (
            f"cd {shlex.quote(root_dir)} && "
            "find . -mindepth 1 -maxdepth 1 -type d "
            "-printf 'DIR\\t%P\\n' | sort"
        )
        output, error = run_remote_command(command)
        outputs.append(f"## {label}\n{output.rstrip()}")
        if error.strip():
            errors.append(f"{label}: {error.rstrip()}")
        for target in _parse_cleanup_targets(output):
            targets.append({
                **target,
                "remote_workdir": root_dir,
                "scope": label,
            })

    return {
        "success": not errors,
        "remote_workdir": None,
        "remote_workdirs": [root for _, root in roots],
        "targets": targets,
        "output": "\n\n".join(outputs),
        "error": "\n".join(errors),
    }


def cleanup_remote_agent_targets(targets):
    safe_targets = [
        target
        for target in targets
        if target.get("kind") in {"dir", "file"}
        and _is_safe_remote_cleanup_target(target.get("path", ""))
        and target.get("remote_workdir", REMOTE_WORKDIR)
    ]

    if not safe_targets:
        return {
            "success": False,
            "remote_workdir": REMOTE_WORKDIR,
            "remote_workdirs": [],
            "deleted": [],
            "output": "",
            "error": "没有安全的可清理目标。",
        }

    grouped_targets = {}
    for target in safe_targets:
        remote_workdir = target.get("remote_workdir") or REMOTE_WORKDIR
        grouped_targets.setdefault(remote_workdir, []).append(target)

    outputs = []
    errors = []

    for remote_workdir, group in grouped_targets.items():
        quoted_targets = " ".join(
            shlex.quote(target["path"])
            for target in group
        )
        command = (
            f"cd {shlex.quote(remote_workdir)} && "
            f"rm -rf -- {quoted_targets}"
        )

        output, error = run_remote_command(command)
        if output.strip():
            outputs.append(f"{remote_workdir}:\n{output.rstrip()}")
        if error.strip():
            errors.append(f"{remote_workdir}:\n{error.rstrip()}")

    return {
        "success": not errors,
        "remote_workdir": REMOTE_WORKDIR,
        "remote_workdirs": sorted(grouped_targets),
        "deleted": safe_targets,
        "output": "\n\n".join(outputs),
        "error": "\n\n".join(errors),
    }


def _read_slurm_file_from_remote_dir(job_id, remote_workdir, extension, title):
    remote_dir = shlex.quote(remote_workdir)
    safe_job_id = shlex.quote(str(job_id))
    command = (
        f"cd {remote_dir} && "
        "{ "
        "echo 'Remote job directory:'; pwd; "
        "echo ''; echo 'Files:'; ls -1; "
        f"echo ''; echo '{title}:'; "
        f"if ls *_{safe_job_id}.{extension} >/dev/null 2>&1; then cat *_{safe_job_id}.{extension}; "
        f"elif ls *.{extension} >/dev/null 2>&1; then cat *.{extension}; "
        f"else echo 'No {title} file found yet.'; fi; "
        "}"
    )

    output, error = run_remote_command(command)

    return {
        "job_id": job_id,
        "output": output,
        "error": error,
    }


def read_job_output(job_id):
    from modules.slurm.job_registry import get_job

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

    if job and job.get("remote_workdir"):
        return _read_slurm_file_from_remote_dir(
            job_id,
            job["remote_workdir"],
            "out",
            "stdout",
        )

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
    from modules.slurm.job_registry import get_job

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

    if job and job.get("remote_workdir"):
        return _read_slurm_file_from_remote_dir(
            job_id,
            job["remote_workdir"],
            "err",
            "stderr",
        )

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
