import re
from pathlib import Path

from modules.core.hpc_config import (
    DEFAULT_PARTITION,
    VASP_LOCAL_JOBS_DIR,
    VASP_LOCAL_OUTPUT_DIR,
    VASP_PARTITION,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
    VASP_REMOTE_WORKDIR,
)
from modules.slurm.slurm_assistant import (
    extract_command,
    extract_cpu_count,
    extract_gpu_count,
    extract_memory,
    extract_time_limit,
    generate_sbatch_script,
)
from modules.core.tool_calling import ToolCall, ToolResult, ensure_allowed_tool
from modules.vasp.vasp_assistant import prepare_vasp_submit_script as prepare_vasp_script


VASP_INPUT_FILES = ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]
SLURM_TOOL_PREPARE = "prepare_slurm_job"
SLURM_TOOL_SUBMIT_PREPARED = "submit_prepared_slurm_job"
VASP_TOOL_PREPARE = "prepare_vasp_job"
VASP_TOOL_SUBMIT_PREPARED = "submit_prepared_vasp_job"
ALLOWED_SLURM_TOOLS = {
    SLURM_TOOL_PREPARE,
    SLURM_TOOL_SUBMIT_PREPARED,
}
ALLOWED_VASP_TOOLS = {
    VASP_TOOL_PREPARE,
    VASP_TOOL_SUBMIT_PREPARED,
}


def add_partition(script: str, partition: str = DEFAULT_PARTITION) -> str:
    partition = (partition or "").strip()

    if not partition:
        return script

    lines = script.splitlines()

    if any(line.strip().startswith("#SBATCH --partition") for line in lines):
        return script

    insert_index = 1 if lines and lines[0].startswith("#!") else 0
    lines.insert(insert_index, f"#SBATCH --partition={partition}")

    return "\n".join(lines) + "\n"


def make_slurm_prepare_tool_call(user_request: str) -> ToolCall:
    return ToolCall(
        tool=SLURM_TOOL_PREPARE,
        arguments={
            "user_request": user_request,
            "command": extract_command(user_request),
            "cpus": extract_cpu_count(user_request),
            "time": extract_time_limit(user_request),
            "memory": extract_memory(user_request),
            "gpu": extract_gpu_count(user_request),
            "partition": DEFAULT_PARTITION or None,
        },
        source="rules",
        confidence=1.0,
        needs_confirmation=True,
    )


def validate_slurm_tool_call(tool_call: dict | ToolCall) -> ToolCall:
    call = ensure_allowed_tool(tool_call, ALLOWED_SLURM_TOOLS)
    arguments = dict(call.arguments)

    if call.tool == SLURM_TOOL_PREPARE:
        user_request = str(arguments.get("user_request") or "").strip()
        if not user_request:
            raise ValueError("普通 Slurm 作业请求不能为空。")

        arguments["user_request"] = user_request
        arguments.setdefault("command", extract_command(user_request))
        arguments.setdefault("cpus", extract_cpu_count(user_request))
        arguments.setdefault("time", extract_time_limit(user_request))
        arguments.setdefault("memory", extract_memory(user_request))
        arguments.setdefault("gpu", extract_gpu_count(user_request))
        arguments.setdefault("partition", DEFAULT_PARTITION or None)

        return ToolCall(
            tool=call.tool,
            arguments=arguments,
            source=call.source,
            confidence=call.confidence,
            needs_confirmation=True,
            metadata=call.metadata,
        )

    if call.tool == SLURM_TOOL_SUBMIT_PREPARED:
        script = str(arguments.get("script") or "")
        if not script.startswith("#!/bin/bash"):
            raise ValueError("待提交脚本不是有效的 sbatch 脚本。")

        arguments["script"] = script
        return ToolCall(
            tool=call.tool,
            arguments=arguments,
            source=call.source,
            confidence=call.confidence,
            needs_confirmation=False,
            metadata=call.metadata,
        )

    raise ValueError(f"不支持的 Slurm 工具: {call.tool}")


def prepare_slurm_job_tool_call(user_request: str) -> ToolCall:
    return validate_slurm_tool_call(make_slurm_prepare_tool_call(user_request))


def execute_prepare_slurm_job_tool_call(tool_call: dict | ToolCall) -> ToolResult:
    call = validate_slurm_tool_call(tool_call)
    user_request = call.arguments["user_request"]
    script = generate_sbatch_script(user_request, allow_llm_fallback=False)

    if not script.startswith("#!/bin/bash"):
        return ToolResult(
            success=False,
            message=script,
            data={
                "ready": False,
                "script": None,
            },
            tool_call=call,
        )

    script = add_partition(script)
    message = (
        "我将把下面的作业提交到超算"
        f"{_partition_message(DEFAULT_PARTITION)}。\n\n{script}\n请确认后再提交。"
    )

    return ToolResult(
        success=True,
        message=message,
        data={
            "ready": True,
            "script": script,
            "message": message,
        },
        tool_call=call,
    )


def prepare_submit_script(user_request: str):
    tool_call = prepare_slurm_job_tool_call(user_request)
    result = execute_prepare_slurm_job_tool_call(tool_call)

    return {
        "ready": bool(result.data.get("ready")),
        "script": result.data.get("script"),
        "message": result.message,
        "tool_call": tool_call.to_dict(),
    }


def make_vasp_prepare_tool_call(user_request: str) -> ToolCall:
    return ToolCall(
        tool=VASP_TOOL_PREPARE,
        arguments={
            "user_request": user_request,
            "partition": VASP_PARTITION or None,
            "local_jobs_dir": str(Path(VASP_LOCAL_JOBS_DIR).resolve()),
            "remote_input_dir": VASP_REMOTE_INPUT_DIR,
            "remote_output_dir": VASP_REMOTE_OUTPUT_DIR,
        },
        source="rules",
        confidence=1.0,
        needs_confirmation=True,
    )


def validate_vasp_tool_call(tool_call: dict | ToolCall) -> ToolCall:
    call = ensure_allowed_tool(tool_call, ALLOWED_VASP_TOOLS)
    arguments = dict(call.arguments)

    if call.tool == VASP_TOOL_PREPARE:
        user_request = str(arguments.get("user_request") or "").strip()
        if not user_request:
            raise ValueError("VASP 作业请求不能为空。")

        arguments["user_request"] = user_request
        arguments.setdefault("partition", VASP_PARTITION or None)
        arguments.setdefault("local_jobs_dir", str(Path(VASP_LOCAL_JOBS_DIR).resolve()))
        arguments.setdefault("remote_input_dir", VASP_REMOTE_INPUT_DIR)
        arguments.setdefault("remote_output_dir", VASP_REMOTE_OUTPUT_DIR)

        return ToolCall(
            tool=call.tool,
            arguments=arguments,
            source=call.source,
            confidence=call.confidence,
            needs_confirmation=True,
            metadata=call.metadata,
        )

    if call.tool == VASP_TOOL_SUBMIT_PREPARED:
        script = str(arguments.get("script") or "")
        if not script.startswith("#!/bin/bash"):
            raise ValueError("待提交 VASP 脚本不是有效的 sbatch 脚本。")

        arguments["script"] = script
        return ToolCall(
            tool=call.tool,
            arguments=arguments,
            source=call.source,
            confidence=call.confidence,
            needs_confirmation=False,
            metadata=call.metadata,
        )

    raise ValueError(f"不支持的 VASP 工具: {call.tool}")


def prepare_vasp_job_tool_call(user_request: str) -> ToolCall:
    return validate_vasp_tool_call(make_vasp_prepare_tool_call(user_request))


def execute_prepare_vasp_job_tool_call(tool_call: dict | ToolCall) -> ToolResult:
    call = validate_vasp_tool_call(tool_call)
    user_request = call.arguments["user_request"]
    prepared = prepare_vasp_script(user_request)

    if not prepared["ready"]:
        return ToolResult(
            success=False,
            message=prepared["message"],
            data={
                **prepared,
                "ready": False,
            },
            tool_call=call,
        )

    script = add_partition(prepared["script"], VASP_PARTITION)
    message = (
        "我将把下面的 VASP 作业提交到超算"
        f"{_partition_message(VASP_PARTITION)}。\n\n"
        "确认提交后，我会从本地 VASP 作业目录中选择一个完整作业目录，"
        "写入 job.sh，并把该目录上传到远端 VASP 输入目录。\n"
        f"本地 VASP 作业目录: {Path(VASP_LOCAL_JOBS_DIR).resolve()}\n"
        "默认选择最近保存的完整 VASP 作业；也可以在请求里写具体子目录名。\n\n"
        f"远程 VASP 输入根目录: {VASP_REMOTE_INPUT_DIR}\n"
        f"远程 VASP 输出根目录: {VASP_REMOTE_OUTPUT_DIR}\n\n"
        "运行时会在输出根目录下创建同名作业目录，并从输入目录复制 INCAR/KPOINTS/POSCAR/POTCAR 后执行 VASP。\n\n"
        f"{script}\n请确认后再提交。"
    )

    return ToolResult(
        success=True,
        message=message,
        data={
            "ready": True,
            "script": script,
            "local_jobs_dir": str(Path(VASP_LOCAL_JOBS_DIR).resolve()),
            "remote_input_dir": VASP_REMOTE_INPUT_DIR,
            "remote_output_dir": VASP_REMOTE_OUTPUT_DIR,
            "remote_workdir": VASP_REMOTE_OUTPUT_DIR,
            "message": message,
        },
        tool_call=call,
    )


def prepare_vasp_submit_script(user_request: str):
    tool_call = prepare_vasp_job_tool_call(user_request)
    result = execute_prepare_vasp_job_tool_call(tool_call)

    return {
        **result.data,
        "ready": bool(result.data.get("ready")),
        "script": result.data.get("script"),
        "message": result.message,
        "tool_call": tool_call.to_dict(),
    }


def _partition_message(partition: str) -> str:
    partition = (partition or "").strip()

    if partition:
        return f" partition：{partition}"

    return "，不指定 partition，使用集群默认分区"


def submit_prepared_script(script: str, uploaded_files=None):
    from modules.slurm.slurm_tools import submit_script_text

    uploaded_files = uploaded_files or []
    result = submit_script_text(script, uploaded_files=uploaded_files)

    if result["success"] and result["job_id"]:
        from modules.slurm.job_registry import register_job

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
    from modules.slurm.job_registry import register_job

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
            "message": "请提供远端 VASP 输出目录名或绝对路径。",
        }

    remote_path = Path(selector)

    if remote_path.is_absolute():
        remote_workdir = str(remote_path)
        local_job_dir = str(Path(VASP_LOCAL_JOBS_DIR) / remote_path.name)
    else:
        remote_workdir = f"{VASP_REMOTE_WORKDIR}/{selector}"
        local_job_dir = str(Path(VASP_LOCAL_JOBS_DIR) / selector)

    local_output_dir = Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / Path(remote_workdir).name
    local_raw_output_dir = local_output_dir / "raw_output"
    local_analysis_dir = local_output_dir / "analysis"
    register_job(
        job_id,
        {
            "type": "vasp",
            "job_id": str(job_id),
            "local_job_dir": local_job_dir,
            "local_output_dir": str(local_output_dir),
            "local_raw_output_dir": str(local_raw_output_dir),
            "local_analysis_dir": str(local_analysis_dir),
            "remote_workdir": remote_workdir,
            "remote_output_dir": remote_workdir,
            "remote_script": f"{remote_workdir}/job.sh",
        },
    )

    return {
        "success": True,
        "message": (
            "VASP 作业映射已登记。\n\n"
            f"Job ID: {job_id}\n"
            f"本地作业目录: {local_job_dir}\n"
            f"本地输出目录: {local_output_dir}\n"
            f"本地原始输出目录: {local_raw_output_dir}\n"
            f"本地分析目录: {local_analysis_dir}\n"
            f"远程输出目录: {remote_workdir}\n\n"
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
            f"请先在 {root.resolve()} 下手动创建包含 "
            "INCAR、POSCAR、POTCAR、KPOINTS 的子目录。"
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

    from modules.slurm.slurm_tools import submit_vasp_script_text

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
        from modules.slurm.job_registry import register_job

        register_job(
            result["job_id"],
            {
                "type": "vasp",
                "job_id": result["job_id"],
                "local_job_dir": result["local_job_dir"],
                "local_output_dir": result.get("local_output_dir"),
                "local_raw_output_dir": result.get("local_raw_output_dir"),
                "local_analysis_dir": result.get("local_analysis_dir"),
                "remote_workdir": result["remote_workdir"],
                "remote_input_dir": result.get("remote_input_dir"),
                "remote_output_dir": result.get("remote_output_dir"),
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
                f"本地 VASP 输入目录: {result['local_job_dir']}\n"
                f"本地 VASP 输出目录: {result.get('local_output_dir')}\n"
                f"本地 VASP 原始输出目录: {result.get('local_raw_output_dir')}\n"
                f"本地分析目录: {result.get('local_analysis_dir')}\n"
                f"远程 VASP 输入目录: {result.get('remote_input_dir')}\n"
                f"远程 VASP 输出目录: {result.get('remote_output_dir')}\n"
                f"远程脚本: {result['remote_script']}\n\n"
                "本地输入文件:\n"
                f"{archived_files}\n\n"
                "已上传到远端输入/输出目录的文件:\n"
                f"{uploaded_files}\n\n"
                "VASP 标准输出、错误日志和运行结果会写入远程输出目录。\n"
                "作业完成后，可同步远端输出到本地输出目录，并在 analysis/ 下生成 Claude Code 分析输入和报告。\n\n"
                f"Slurm 输出:\n{result['output']}"
            ),
            "raw": result,
        }

    return {
        "success": False,
        "job_id": result["job_id"],
        "answer": (
            "VASP 作业提交失败。\n\n"
            f"本地 VASP 输入目录: {result.get('local_job_dir')}\n"
            f"远程 VASP 输入目录: {result.get('remote_input_dir')}\n"
            f"远程 VASP 输出目录: {result.get('remote_output_dir')}\n"
            f"Slurm 输出:\n{result['output']}\n"
            f"错误信息:\n{result['error']}"
        ),
        "raw": result,
    }
