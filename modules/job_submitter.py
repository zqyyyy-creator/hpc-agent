import os
import re
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv

from modules.slurm_assistant import generate_sbatch_script
from modules.vasp_assistant import prepare_vasp_submit_script as prepare_vasp_script


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_PARTITION = os.getenv("HPC_DEFAULT_PARTITION", "amd_test")
VASP_PARTITION = os.getenv("HPC_VASP_PARTITION", DEFAULT_PARTITION)
VASP_LOCAL_JOBS_DIR = os.getenv("HPC_LOCAL_VASP_JOBS_DIR", "/home/lenovo/vasp-jobs")
VASP_LOCAL_IMPORT_DIR = os.getenv("HPC_LOCAL_VASP_IMPORT_DIR", "/home/lenovo/vasp-jobs-input")
VASP_REMOTE_WORKDIR = os.getenv("HPC_VASP_REMOTE_WORKDIR", os.getenv("HPC_REMOTE_WORKDIR"))
VASP_INPUT_FILES = ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]
VASP_INPUT_BLOCK_PATTERN = re.compile(
    r"```[ \t]*(INCAR|POSCAR|POTCAR|KPOINTS)[^\n]*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def add_partition(script: str, partition: str = DEFAULT_PARTITION) -> str:
    lines = script.splitlines()

    if any(line.strip().startswith("#SBATCH --partition") for line in lines):
        return script

    insert_index = 1 if lines and lines[0].startswith("#!") else 0
    lines.insert(insert_index, f"#SBATCH --partition={partition}")

    return "\n".join(lines) + "\n"


def prepare_submit_script(user_request: str):
    script = generate_sbatch_script(user_request)

    if not script.startswith("#!/bin/bash"):
        return {
            "ready": False,
            "script": None,
            "message": script,
        }

    script = add_partition(script)

    return {
        "ready": True,
        "script": script,
        "message": (
            "我将把下面的作业提交到超算 partition："
            f"{DEFAULT_PARTITION}\n\n{script}\n请确认后再提交。"
        ),
    }


def prepare_vasp_submit_script(user_request: str):
    prepared = prepare_vasp_script(user_request)

    if not prepared["ready"]:
        return prepared

    script = add_partition(prepared["script"], VASP_PARTITION)

    return {
        "ready": True,
        "script": script,
        "local_jobs_dir": str(Path(VASP_LOCAL_JOBS_DIR).resolve()),
        "remote_workdir": VASP_REMOTE_WORKDIR,
        "message": (
            "我将把下面的 VASP 作业提交到超算 partition："
            f"{VASP_PARTITION}\n\n"
            "确认提交后，我会从本地 VASP 作业目录中选择一个完整作业目录，"
            "写入 job.sh，然后上传到远端独立目录。\n"
            f"本地 VASP 作业目录: {Path(VASP_LOCAL_JOBS_DIR).resolve()}\n"
            "默认选择最近保存的完整 VASP 作业；也可以在请求里写具体子目录名。\n\n"
            f"远程 VASP 作业根目录: {VASP_REMOTE_WORKDIR}\n\n"
            f"{script}\n请确认后再提交。"
        ),
    }


def submit_prepared_script(script: str, uploaded_files=None):
    from modules.slurm_tools import submit_script_text

    uploaded_files = uploaded_files or []
    result = submit_script_text(script, uploaded_files=uploaded_files)

    if result["success"] and result["job_id"]:
        from modules.job_registry import register_job

        remote_uploaded_files = result.get("uploaded_files", [])

        register_job(
            result["job_id"],
            {
                "type": "slurm",
                "job_id": result["job_id"],
                "remote_workdir": result["remote_workdir"],
                "remote_script": result["remote_script"],
                "uploaded_files": remote_uploaded_files,
            },
        )

        uploaded_summary = "\n".join(f"- {path}" for path in remote_uploaded_files)

        return {
            "success": True,
            "job_id": result["job_id"],
            "answer": (
                "作业已提交成功。\n\n"
                f"Job ID: {result['job_id']}\n"
                f"远程作业目录: {result['remote_workdir']}\n"
                f"远程脚本: {result['remote_script']}\n\n"
                "脚本、标准输出和错误日志会保存在这个远程作业目录中。\n\n"
                "已上传文件:\n"
                f"{uploaded_summary}\n\n"
                f"Slurm 输出:\n{result['output']}"
            ),
            "raw": result,
        }

    return {
        "success": False,
        "job_id": result["job_id"],
        "answer": (
            "作业提交失败。\n\n"
            f"Slurm 输出:\n{result['output']}\n"
            f"错误信息:\n{result['error']}"
        ),
        "raw": result,
    }


def validate_vasp_input_files(input_dir: str):
    base_dir = Path(input_dir)
    missing_files = [
        name
        for name in VASP_INPUT_FILES
        if not (base_dir / name).is_file()
    ]

    return {
        "input_dir": base_dir,
        "missing_files": missing_files,
    }


def has_complete_vasp_inputs(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in VASP_INPUT_FILES)


def list_vasp_job_dirs(jobs_dir: str = VASP_LOCAL_JOBS_DIR):
    root = Path(jobs_dir)

    if not root.is_dir():
        return []

    candidates = [
        path
        for path in root.iterdir()
        if has_complete_vasp_inputs(path)
    ]

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates


def extract_vasp_job_selector(text: str):
    path = extract_source_dir_from_text(text)
    if path:
        return path

    patterns = [
        r"(?:作业目录|子目录|目录名|编号|job)\s*[:：=]?\s*([A-Za-z0-9_.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def register_existing_vasp_job_from_text(text: str):
    from modules.job_registry import register_vasp_job

    job_match = re.search(r"(\d{4,})", text)

    if not job_match:
        return {
            "success": False,
            "message": "请提供 job id，例如：登记 VASP 作业 11817144，目录名 vasp_imported_xxx。",
        }

    job_id = job_match.group(1)
    selector = extract_vasp_job_selector(text)

    if not selector:
        return {
            "success": False,
            "message": "请提供远端 VASP 作业目录名或绝对路径。",
        }

    remote_path = Path(selector)

    if remote_path.is_absolute():
        remote_workdir = str(remote_path)
        local_job_dir = str(Path(VASP_LOCAL_JOBS_DIR) / remote_path.name)
    else:
        remote_workdir = f"{VASP_REMOTE_WORKDIR}/{selector}"
        local_job_dir = str(Path(VASP_LOCAL_JOBS_DIR) / selector)

    register_vasp_job(job_id, local_job_dir, remote_workdir)

    return {
        "success": True,
        "message": (
            "VASP 作业映射已登记。\n\n"
            f"Job ID: {job_id}\n"
            f"本地作业目录: {local_job_dir}\n"
            f"远程作业目录: {remote_workdir}\n\n"
            f"现在可以读取 {job_id} 的输出或错误日志。"
        ),
    }


def resolve_vasp_job_input_dir(
    selector_text: str = "",
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
):
    root = Path(jobs_dir)
    selector = extract_vasp_job_selector(selector_text)

    if selector:
        selected_path = Path(selector)

        if selected_path.is_absolute():
            validation = validate_vasp_input_files(str(selected_path))

            return {
                "success": not validation["missing_files"],
                "input_dir": selected_path,
                "missing_files": validation["missing_files"],
                "message": (
                    f"使用指定 VASP 作业目录: {selected_path}"
                    if not validation["missing_files"]
                    else f"指定 VASP 作业目录不完整: {selected_path}"
                ),
            }

        selected_path = root / selector
        validation = validate_vasp_input_files(str(selected_path))

        return {
            "success": not validation["missing_files"],
            "input_dir": selected_path,
            "missing_files": validation["missing_files"],
            "message": (
                f"使用指定 VASP 作业子目录: {selected_path}"
                if not validation["missing_files"]
                else f"指定 VASP 作业子目录不完整: {selected_path}"
            ),
        }

    candidates = list_vasp_job_dirs(str(root))

    if candidates:
        return {
            "success": True,
            "input_dir": candidates[0],
            "missing_files": [],
            "message": f"使用最近保存的 VASP 作业目录: {candidates[0]}",
        }

    return {
        "success": False,
        "input_dir": root,
        "missing_files": VASP_INPUT_FILES,
        "message": (
            "本地 VASP 作业目录中没有找到完整作业。\n"
            f"请先在 {root.resolve()} 下生成或导入包含 "
            "INCAR、POSCAR、POTCAR、KPOINTS 的子目录。"
        ),
    }


def parse_vasp_input_blocks(text: str):
    inputs = {}

    for match in VASP_INPUT_BLOCK_PATTERN.finditer(text):
        name = match.group(1).upper()
        content = match.group(2).strip("\n") + "\n"
        inputs[name] = content

    return inputs


def create_vasp_inputs_from_text(
    text: str,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
    job_name: str = "vasp_inputs",
):
    inputs = parse_vasp_input_blocks(text)
    missing_files = [
        name
        for name in VASP_INPUT_FILES
        if name not in inputs
    ]

    if missing_files:
        return {
            "success": False,
            "local_input_dir": None,
            "written_files": [],
            "missing_files": missing_files,
            "message": (
                "没有生成 VASP 输入文件，因为缺少这些代码块: "
                + ", ".join(missing_files)
                + "\n\n请按这种格式提供四个文件内容:\n"
                "```INCAR\n...\n```\n"
                "```POSCAR\n...\n```\n"
                "```POTCAR\n...\n```\n"
                "```KPOINTS\n...\n```"
            ),
        }

    archive_root = Path(jobs_dir)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_job_name = _safe_job_dir_name(job_name)
    local_input_dir = archive_root / f"{safe_job_name}_{timestamp}"

    archive_root.mkdir(parents=True, exist_ok=True)

    suffix = 1
    while local_input_dir.exists():
        local_input_dir = archive_root / f"{safe_job_name}_{timestamp}_{suffix}"
        suffix += 1

    local_input_dir.mkdir()

    written_files = []
    for name in VASP_INPUT_FILES:
        path = local_input_dir / name
        path.write_text(inputs[name], encoding="utf-8")
        written_files.append(str(path))

    return {
        "success": True,
        "local_input_dir": local_input_dir,
        "written_files": written_files,
        "missing_files": [],
        "message": (
            "VASP 输入文件已生成。\n\n"
            f"本地目录: {local_input_dir}\n"
            "已写入文件:\n"
            + "\n".join(f"- {path}" for path in written_files)
            + "\n\n如果要提交这套输入文件，可以说："
            f"\n帮我提交 VASP 作业，目录名 {local_input_dir.name}"
            "\n也可以直接说“提交最近的 VASP 作业”。"
        ),
    }


def _create_unique_vasp_dir(root_dir: str, job_name: str):
    archive_root = Path(root_dir)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe_job_name = _safe_job_dir_name(job_name)
    local_dir = archive_root / f"{safe_job_name}_{timestamp}"

    archive_root.mkdir(parents=True, exist_ok=True)

    suffix = 1
    while local_dir.exists():
        local_dir = archive_root / f"{safe_job_name}_{timestamp}_{suffix}"
        suffix += 1

    local_dir.mkdir()
    return local_dir


def write_vasp_input_files(
    inputs: dict,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
    job_name: str = "vasp_inputs",
    require_all: bool = True,
):
    missing_files = [
        name
        for name in VASP_INPUT_FILES
        if name not in inputs
    ]

    if require_all and missing_files:
        return {
            "success": False,
            "local_input_dir": None,
            "written_files": [],
            "missing_files": missing_files,
            "message": "缺少 VASP 输入文件: " + ", ".join(missing_files),
        }

    local_input_dir = _create_unique_vasp_dir(jobs_dir, job_name)
    written_files = []

    for name in VASP_INPUT_FILES:
        if name not in inputs:
            continue

        path = local_input_dir / name
        content = inputs[name].rstrip("\n") + "\n"
        path.write_text(content, encoding="utf-8")
        written_files.append(str(path))

    return {
        "success": True,
        "local_input_dir": local_input_dir,
        "written_files": written_files,
        "missing_files": missing_files,
        "message": (
            "VASP 输入文件已写入。\n\n"
            f"本地目录: {local_input_dir}\n"
            "已写入文件:\n"
            + "\n".join(f"- {path}" for path in written_files)
        ),
    }


def import_vasp_inputs_from_dir(
    source_dir: str = VASP_LOCAL_IMPORT_DIR,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
    job_name: str = "vasp_imported",
):
    validation = validate_vasp_input_files(source_dir)

    if validation["missing_files"]:
        return {
            "success": False,
            "local_input_dir": None,
            "written_files": [],
            "missing_files": validation["missing_files"],
            "message": (
                "没有导入 VASP 输入文件，因为源目录不完整。\n\n"
                f"源目录: {validation['input_dir'].resolve()}\n"
                f"缺少文件: {', '.join(validation['missing_files'])}"
            ),
        }

    local_input_dir = _create_unique_vasp_dir(jobs_dir, job_name)
    written_files = []

    for name in VASP_INPUT_FILES:
        source_path = validation["input_dir"] / name
        target_path = local_input_dir / name
        shutil.copy2(source_path, target_path)
        written_files.append(str(target_path))

    return {
        "success": True,
        "local_input_dir": local_input_dir,
        "written_files": written_files,
        "missing_files": [],
        "message": (
            "VASP 输入文件已从目录导入。\n\n"
            f"源目录: {validation['input_dir'].resolve()}\n"
            f"本地作业目录: {local_input_dir}\n"
            "已导入文件:\n"
            + "\n".join(f"- {path}" for path in written_files)
            + "\n\n如果要提交这套输入文件，可以说："
            f"\n帮我提交 VASP 作业，目录名 {local_input_dir.name}"
            "\n也可以直接说“提交最近的 VASP 作业”。"
        ),
    }


def extract_source_dir_from_text(text: str):
    patterns = [
        r"(\/[^\s，,。]+)",
        r"(?:目录|路径|dir|directory)\s*[:：=]\s*([^\s，,。]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def import_vasp_inputs_from_text(text: str):
    source_dir = extract_source_dir_from_text(text) or VASP_LOCAL_IMPORT_DIR
    return import_vasp_inputs_from_dir(source_dir)


def generate_vasp_template_inputs(
    user_request: str,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
    job_name: str = "vasp_template",
):
    request = user_request.lower()
    is_static = "静态" in user_request or "static" in request
    is_relax = "结构优化" in user_request or "relax" in request or not is_static

    incar_lines = [
        "SYSTEM = generated_vasp_job",
        "ENCUT = 520",
        "EDIFF = 1E-5",
        "ISMEAR = 0",
        "SIGMA = 0.05",
    ]

    if is_static:
        incar_lines.extend([
            "IBRION = -1",
            "NSW = 0",
        ])
    elif is_relax:
        incar_lines.extend([
            "EDIFFG = -0.02",
            "IBRION = 2",
            "NSW = 50",
            "ISIF = 3",
        ])

    kpoints = "\n".join([
        "Automatic mesh",
        "0",
        "Gamma",
        "3 3 3",
        "0 0 0",
    ])

    inputs = {
        "INCAR": "\n".join(incar_lines),
        "KPOINTS": kpoints,
    }

    if "si" in request or "硅" in user_request:
        inputs["POSCAR"] = "\n".join([
            "Si",
            "1.0",
            "3.84 0.00 0.00",
            "0.00 3.84 0.00",
            "0.00 0.00 3.84",
            "Si",
            "2",
            "Direct",
            "0.00 0.00 0.00",
            "0.25 0.25 0.25",
        ])

    result = write_vasp_input_files(
        inputs,
        jobs_dir=jobs_dir,
        job_name=job_name,
        require_all=False,
    )
    missing = [
        name
        for name in VASP_INPUT_FILES
        if name not in inputs
    ]
    result["missing_files"] = missing
    result["success"] = True
    result["message"] = (
        "Agent 已生成安全的 VASP 输入模板。\n\n"
        f"本地目录: {result['local_input_dir']}\n"
        "已生成文件:\n"
        + "\n".join(f"- {path}" for path in result["written_files"])
    )

    if missing:
        result["message"] += (
            "\n\n仍需你补充这些文件后才能提交: "
            + ", ".join(missing)
        )

    result["message"] += (
        "\n\n注意: Agent 不会伪造 POTCAR。POTCAR 需要来自你有权限使用的 VASP 赝势库。"
    )
    return result


def _extract_job_name(script: str, default: str = "vasp_job") -> str:
    match = re.search(r"^#SBATCH\s+--job-name=([A-Za-z0-9_.-]+)\s*$", script, re.MULTILINE)
    if match:
        return match.group(1)

    return default


def _safe_job_dir_name(name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe_name or "vasp_job"


def create_vasp_local_job_dir(
    script: str,
    input_dir: str = None,
    jobs_dir: str = VASP_LOCAL_JOBS_DIR,
):
    if input_dir is None:
        resolved = resolve_vasp_job_input_dir("", jobs_dir)

        if not resolved["success"]:
            raise ValueError(resolved["message"])

        source_dir = resolved["input_dir"]
    else:
        source_dir = Path(input_dir)

    archive_root = Path(jobs_dir)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    job_name = _safe_job_dir_name(_extract_job_name(script))
    local_job_dir = archive_root / f"{job_name}_{timestamp}"

    archive_root.mkdir(parents=True, exist_ok=True)

    suffix = 1
    while local_job_dir.exists():
        local_job_dir = archive_root / f"{job_name}_{timestamp}_{suffix}"
        suffix += 1

    local_job_dir.mkdir()

    archived_files = []
    for name in VASP_INPUT_FILES:
        source_path = source_dir / name
        target_path = local_job_dir / name
        shutil.copy2(source_path, target_path)
        archived_files.append(str(target_path))

    job_script_path = local_job_dir / "job.sh"
    job_script_path.write_text(script, encoding="utf-8")
    archived_files.append(str(job_script_path))

    return {
        "local_job_dir": local_job_dir,
        "archived_files": archived_files,
    }


def submit_prepared_vasp_script(script: str, selector_text: str = ""):
    resolved = resolve_vasp_job_input_dir(selector_text)

    if not resolved["success"]:
        missing = ", ".join(resolved["missing_files"])
        return {
            "success": False,
            "job_id": None,
            "answer": (
                "VASP 作业未提交，因为没有找到可提交的本地 VASP 作业目录。\n\n"
                f"{resolved['message']}\n"
                f"检查目录: {resolved['input_dir'].resolve()}\n"
                f"缺少文件: {missing}\n\n"
                "请先手动粘贴生成、从导入目录导入，或用 Agent 辅助生成模板并补齐缺失文件。"
            ),
            "raw": {
                "missing_files": resolved["missing_files"],
            },
        }

    from modules.slurm_tools import submit_vasp_script_text

    local_job_dir = resolved["input_dir"]
    local_job_script = local_job_dir / "job.sh"
    local_job_script.write_text(script, encoding="utf-8")

    result = submit_vasp_script_text(
        script,
        local_job_dir,
        run_name=local_job_dir.name,
    )
    result["local_job_dir"] = str(local_job_dir)
    result["archived_files"] = [
        str(local_job_dir / name)
        for name in VASP_INPUT_FILES
    ] + [str(local_job_script)]

    if result["success"] and result["job_id"]:
        from modules.job_registry import register_job

        register_job(
            result["job_id"],
            {
                "type": "vasp",
                "job_id": result["job_id"],
                "local_job_dir": result["local_job_dir"],
                "remote_workdir": result["remote_workdir"],
                "remote_script": result["remote_script"],
                "uploaded_files": result.get("uploaded_files", []),
            },
        )

        uploaded_files = "\n".join([
            f"- {path}"
            for path in result.get("uploaded_files", [])
        ])
        archived_files = "\n".join([
            f"- {path}"
            for path in result.get("archived_files", [])
        ])

        return {
            "success": True,
            "job_id": result["job_id"],
            "answer": (
                "VASP 作业已提交成功。\n\n"
                f"Job ID: {result['job_id']}\n"
                f"本地作业归档目录: {result['local_job_dir']}\n"
                f"远程作业目录: {result['remote_workdir']}\n"
                f"远程脚本: {result['remote_script']}\n\n"
                "本地已归档文件:\n"
                f"{archived_files}\n\n"
                "已上传文件:\n"
                f"{uploaded_files}\n\n"
                "VASP 输出结果也会写入这个远程作业目录。\n\n"
                f"Slurm 输出:\n{result['output']}"
            ),
            "raw": result,
        }

    return {
        "success": False,
        "job_id": result["job_id"],
        "answer": (
            "VASP 作业提交失败。\n\n"
            f"本地作业归档目录: {result.get('local_job_dir')}\n"
            f"远程作业目录: {result.get('remote_workdir')}\n"
            f"Slurm 输出:\n{result['output']}\n"
            f"错误信息:\n{result['error']}"
        ),
        "raw": result,
    }
