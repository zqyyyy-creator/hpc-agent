import fnmatch
import json
import stat
from pathlib import Path

from modules.core.hpc_config import VASP_LOCAL_OUTPUT_DIR
from modules.slurm.remote import get_ssh_client
from modules.slurm.remote_utils import emit_progress


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


def local_vasp_output_dir_for_remote(remote_output_dir: str) -> Path:
    run_name = Path(remote_output_dir).name
    return Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / run_name


def resolve_vasp_local_output_dir(
    remote_output_dir: str,
    preferred_local_output_dir: str | Path | None = None,
) -> Path:
    canonical = local_vasp_output_dir_for_remote(remote_output_dir)

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


def local_vasp_raw_output_dir(local_job_dir: Path) -> Path:
    return local_job_dir / "raw_output"


def should_sync_vasp_output_file(file_name: str) -> bool:
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in VASP_SYNC_EXCLUDE_PATTERNS):
        return False

    return any(fnmatch.fnmatch(file_name, pattern) for pattern in VASP_SYNC_INCLUDE_PATTERNS)


def sftp_file_size(attr) -> int:
    return int(getattr(attr, "st_size", 0) or 0)


def write_vasp_file_manifest(local_job_dir: Path, files: list[dict]) -> Path:
    analysis_dir = local_job_dir / "analysis"
    raw_output_dir = local_vasp_raw_output_dir(local_job_dir)
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


def has_meaningful_vasp_synced_files(files: list[dict]) -> bool:
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
    local_job_dir = Path(local_output_dir).expanduser() if local_output_dir else local_vasp_output_dir_for_remote(remote_output_dir)
    local_raw_output_dir = local_vasp_raw_output_dir(local_job_dir)
    local_job_dir.mkdir(parents=True, exist_ok=True)
    local_raw_output_dir.mkdir(parents=True, exist_ok=True)
    (local_job_dir / "analysis").mkdir(parents=True, exist_ok=True)

    client = get_ssh_client()
    sftp = client.open_sftp()
    synced_files = []
    skipped_files = []

    try:
        emit_progress(progress_callback, "扫描远端 VASP 输出目录中...")
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
                    "size_bytes": sftp_file_size(attr),
                })
                continue

            if not should_sync_vasp_output_file(file_name):
                skipped_files.append({
                    "name": file_name,
                    "reason": "not_in_sync_whitelist_or_excluded",
                    "size_bytes": sftp_file_size(attr),
                })
                continue

            local_path = local_raw_output_dir / file_name
            emit_progress(progress_callback, f"同步 VASP 输出文件: {file_name}")
            sftp.get(remote_path, str(local_path))
            synced_files.append({
                "name": file_name,
                "remote_path": remote_path,
                "local_path": str(local_path),
                "size_bytes": sftp_file_size(attr),
            })
    finally:
        sftp.close()
        client.close()

    if not has_meaningful_vasp_synced_files(synced_files):
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

    manifest_path = write_vasp_file_manifest(local_job_dir, synced_files)
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

    local_output_dir = resolve_vasp_local_output_dir(
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
