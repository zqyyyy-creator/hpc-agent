import re
from pathlib import Path


def _format_remote_access_error(action: str, error: Exception) -> str:
    error_type = type(error).__name__
    return (
        f"{action}失败，无法访问远端 HPC 环境。\n\n"
        "请检查本地 .env 中的这些配置是否完整且对当前 Web 服务进程可用:\n"
        "- HPC_HOST\n"
        "- HPC_USERNAME\n"
        "- HPC_KEY_PATH\n"
        "- HPC_REMOTE_WORKDIR\n\n"
        f"程序捕获到的错误: {error_type}: {error}"
    )


def extract_job_id(text: str):
    match = re.search(r"(\d{4,})", text)

    if match:
        return match.group(1)

    return None


def format_tool_result(title: str, result: dict) -> str:
    lines = [
        title,
        "",
        f"Job ID: {result['job_id']}",
    ]

    if result.get("output"):
        lines.extend(["", "输出:", result["output"].rstrip()])

    if result.get("error"):
        lines.extend(["", "错误:", result["error"].rstrip()])

    if not result.get("output") and not result.get("error"):
        lines.extend(["", "没有返回内容。"])

    return "\n".join(lines)


def query_remote_agent_jobs():
    from modules.slurm_tools import list_remote_agent_jobs

    try:
        result = list_remote_agent_jobs()
    except Exception as error:
        return _format_remote_access_error("读取远端 hpc-agent-jobs 目录", error)

    if result.get("error", "").strip():
        return (
            "读取远端 hpc-agent-jobs 目录失败。\n\n"
            f"远端目录: {result['remote_workdir']}\n\n"
            f"错误:\n{result['error'].rstrip()}"
        )

    output = result.get("output", "").strip()

    if not output:
        return (
            "远端 hpc-agent-jobs 目录下没有找到 Agent 作业文件。\n\n"
            f"远端目录: {result['remote_workdir']}"
        )

    jobs = {}

    for line in output.splitlines():
        path = line.strip()
        match = re.search(r"_(\d+)\.(?:out|err)$", path)

        if not match:
            continue

        job_id = match.group(1)
        directory = path.rsplit("/", 1)[0] if "/" in path else "."
        jobs.setdefault(job_id, {
            "directory": directory,
            "files": [],
        })
        jobs[job_id]["files"].append(path)

    if not jobs:
        return (
            "远端 hpc-agent-jobs 目录下找到了文件，但没有从 .out/.err 文件名中解析到 Job ID。\n\n"
            f"远端目录: {result['remote_workdir']}\n\n"
            f"文件:\n{output}"
        )

    lines = [
        "远端 hpc-agent-jobs 作业编号",
        "",
        f"远端根目录: {result['remote_workdir']}",
        "",
    ]

    for job_id in sorted(jobs):
        job = jobs[job_id]
        lines.append(f"- Job ID: {job_id}")
        lines.append(f"  目录: {job['directory']}")
        lines.append("  文件:")

        for file_path in sorted(job["files"]):
            lines.append(f"  - {file_path}")

        lines.append("")

    return "\n".join(lines).rstrip()


def _extract_vasp_remote_scope(text: str):
    normalized = text.lower().replace(" ", "")

    if any(keyword in normalized for keyword in ["仅input", "只input", "input目录", "输入目录", "输入文件"]):
        return "input"

    if any(keyword in normalized for keyword in ["仅output", "只output", "output目录", "输出目录", "输出结果"]):
        return "output"

    return "both"


def _format_cleanup_targets_with_roots(targets):
    if not targets:
        return "无"

    return "\n".join(
        f"- {target.get('scope', 'remote')}: {target.get('remote_workdir')} / {target['path']}"
        for target in targets
    )


def query_remote_vasp_jobs():
    from modules.slurm_tools import list_remote_vasp_jobs

    try:
        result = list_remote_vasp_jobs()
    except Exception as error:
        return _format_remote_access_error("读取远端 VASP input/output 目录", error)

    if result.get("error", "").strip():
        return (
            "读取远端 VASP 作业目录时有错误。\n\n"
            f"远端 input 目录: {result.get('remote_input_dir')}\n"
            f"远端 output 目录: {result.get('remote_output_dir')}\n\n"
            f"错误:\n{result['error'].rstrip()}"
        )

    output = result.get("output", "").strip()

    if not output:
        return (
            "远端 VASP input/output 目录下没有找到作业目录。\n\n"
            f"远端 input 目录: {result.get('remote_input_dir')}\n"
            f"远端 output 目录: {result.get('remote_output_dir')}"
        )

    return (
        "远端 VASP 作业目录\n\n"
        f"远端 input 目录: {result.get('remote_input_dir')}\n"
        f"远端 output 目录: {result.get('remote_output_dir')}\n\n"
        f"{output}"
    )


def _format_cleanup_targets(targets):
    if not targets:
        return "无"

    return "\n".join(
        f"- {target['kind']}: {target['path']}"
        for target in targets
    )


def _extract_vasp_cleanup_selector(text: str):
    job_id = extract_job_id(text)

    if job_id:
        return job_id

    patterns = [
        r"(?:目录名|作业名|job name|job|作业)\s*[:：=]?\s*([A-Za-z0-9_.-]+)",
        r"vasp\s*([A-Za-z0-9_.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = match.group(1)
            if value.lower() not in {"input", "output", "作业", "任务", "job"}:
                return value

    return None


def prepare_cleanup_remote_job(job_id: str):
    from modules.slurm_tools import find_remote_agent_job_cleanup_targets

    result = find_remote_agent_job_cleanup_targets(job_id)

    if not result["success"]:
        return {
            "ready": False,
            "job_id": job_id,
            "targets": [],
            "message": (
                "无法扫描远端普通作业目录。\n\n"
                f"远端目录: {result['remote_workdir']}\n"
                f"错误:\n{result['error'].rstrip()}"
            ),
        }

    if not result["targets"]:
        return {
            "ready": False,
            "job_id": job_id,
            "targets": [],
            "message": (
                f"没有在远端普通作业目录中找到 Job ID {job_id} 对应的文件。\n\n"
                f"远端目录: {result['remote_workdir']}"
            ),
        }

    return {
        "ready": True,
        "job_id": job_id,
        "remote_workdir": result["remote_workdir"],
        "targets": result["targets"],
        "message": (
            f"准备清理普通作业 Job ID {job_id} 的远端文件。\n\n"
            f"远端根目录: {result['remote_workdir']}\n\n"
            "将删除这些目标:\n"
            f"{_format_cleanup_targets(result['targets'])}\n\n"
            "不会清理 VASP 作业目录。\n"
            "确认后请回复：确认清理"
        ),
    }


def prepare_cleanup_all_remote_jobs():
    from modules.slurm_tools import find_all_remote_agent_cleanup_targets

    result = find_all_remote_agent_cleanup_targets()

    if not result["success"]:
        return {
            "ready": False,
            "targets": [],
            "message": (
                "无法扫描远端普通作业根目录。\n\n"
                f"远端目录: {result['remote_workdir']}\n"
                f"错误:\n{result['error'].rstrip()}"
            ),
        }

    if not result["targets"]:
        return {
            "ready": False,
            "targets": [],
            "message": (
                "远端普通作业根目录下没有可清理的文件或子目录。\n\n"
                f"远端目录: {result['remote_workdir']}"
            ),
        }

    return {
        "ready": True,
        "remote_workdir": result["remote_workdir"],
        "targets": result["targets"],
        "message": (
            "准备清理远端普通作业根目录下的所有一级内容。\n\n"
            f"远端根目录: {result['remote_workdir']}\n\n"
            "将删除这些目标:\n"
            f"{_format_cleanup_targets(result['targets'])}\n\n"
            "会保留远端根目录本身，不会清理 VASP 作业目录。\n"
            "这是高风险操作，确认后必须回复完整短语：确认清理全部"
        ),
    }


def prepare_cleanup_remote_vasp_job(text: str):
    from modules.slurm_tools import find_remote_vasp_job_cleanup_targets

    selector = _extract_vasp_cleanup_selector(text)
    scope = _extract_vasp_remote_scope(text)

    if not selector:
        return {
            "ready": False,
            "targets": [],
            "message": (
                "请提供要清理的 VASP Job ID 或作业目录名，例如：\n"
                "- 清理远端 VASP 作业 11817627 的 input 和 output\n"
                "- 删除远端 VASP 作业 si_static_test 的 output 目录"
            ),
        }

    result = find_remote_vasp_job_cleanup_targets(selector, scope=scope)

    if not result["success"]:
        return {
            "ready": False,
            "selector": selector,
            "targets": [],
            "message": (
                "无法扫描远端 VASP 作业目录。\n\n"
                f"扫描范围: {scope}\n"
                f"远端目录: {', '.join(result.get('remote_workdirs', []))}\n"
                f"错误:\n{result['error'].rstrip()}"
            ),
        }

    if not result["targets"]:
        return {
            "ready": False,
            "selector": selector,
            "targets": [],
            "message": (
                f"没有找到 VASP 作业 {selector} 对应的远端目录。\n\n"
                f"扫描范围: {scope}\n"
                f"远端目录: {', '.join(result.get('remote_workdirs', []))}"
            ),
        }

    return {
        "ready": True,
        "kind": "vasp_job",
        "selector": selector,
        "scope": scope,
        "targets": result["targets"],
        "message": (
            f"准备清理远端 VASP 作业 {selector}。\n\n"
            f"扫描范围: {scope}\n\n"
            "将删除这些目标:\n"
            f"{_format_cleanup_targets_with_roots(result['targets'])}\n\n"
            "确认后请回复：确认清理"
        ),
    }


def prepare_cleanup_all_remote_vasp_jobs(text: str):
    from modules.slurm_tools import find_all_remote_vasp_cleanup_targets

    scope = _extract_vasp_remote_scope(text)
    result = find_all_remote_vasp_cleanup_targets(scope=scope)

    if not result["success"]:
        return {
            "ready": False,
            "targets": [],
            "message": (
                "无法扫描远端 VASP 作业目录。\n\n"
                f"扫描范围: {scope}\n"
                f"远端目录: {', '.join(result.get('remote_workdirs', []))}\n"
                f"错误:\n{result['error'].rstrip()}"
            ),
        }

    if not result["targets"]:
        return {
            "ready": False,
            "targets": [],
            "message": (
                "远端 VASP 作业目录下没有可清理的子目录。\n\n"
                f"扫描范围: {scope}\n"
                f"远端目录: {', '.join(result.get('remote_workdirs', []))}"
            ),
        }

    return {
        "ready": True,
        "kind": "vasp_all",
        "scope": scope,
        "targets": result["targets"],
        "message": (
            "准备清理远端全部 VASP 作业目录。\n\n"
            f"扫描范围: {scope}\n\n"
            "将删除这些目标:\n"
            f"{_format_cleanup_targets_with_roots(result['targets'])}\n\n"
            "这是高风险操作，确认后必须回复完整短语：确认清理全部"
        ),
    }


def execute_cleanup_remote_jobs(targets):
    from modules.slurm_tools import cleanup_remote_agent_targets

    result = cleanup_remote_agent_targets(targets)
    deleted = _format_cleanup_targets_with_roots(result.get("deleted", []))
    remote_locations = "\n".join(
        f"- {path}"
        for path in result.get("remote_workdirs", [])
    ) or f"- {result.get('remote_workdir')}"

    if result["success"]:
        return (
            "远端作业文件已清理。\n\n"
            f"远端根目录:\n{remote_locations}\n\n"
            "已删除:\n"
            f"{deleted}"
        )

    return (
        "远端作业文件清理失败。\n\n"
        f"远端根目录:\n{remote_locations}\n\n"
        "尝试删除:\n"
        f"{deleted}\n\n"
        f"错误:\n{result['error'].rstrip()}"
    )


def query_job_status(job_id: str):
    from modules.slurm_tools import check_job

    result = check_job(job_id)

    if result["output"].strip():
        return format_tool_result("作业状态查询结果", result)

    return (
        "当前 squeue 没有查到这个作业，可能已经结束或 job_id 不存在。\n\n"
        f"Job ID: {job_id}\n"
        "可以在超算上使用 sacct 进一步查看历史状态。"
    )


def query_job_output(job_id: str):
    from modules.slurm_tools import read_job_output

    result = read_job_output(job_id)
    return format_tool_result("作业标准输出", result)


def query_job_error(job_id: str):
    from modules.slurm_tools import read_job_error

    result = read_job_error(job_id)
    return format_tool_result("作业错误日志", result)


def sync_vasp_job_output(job_id: str):
    from modules.slurm_tools import sync_vasp_job_output as sync_remote_output

    try:
        result = sync_remote_output(job_id)
    except Exception as error:
        return _format_remote_access_error("同步远端 VASP 输出", error)

    if not result["success"]:
        return (
            "VASP 输出同步失败。\n\n"
            f"Job ID: {job_id}\n"
            f"远端输出目录: {result.get('remote_output_dir')}\n"
            f"本地输出目录: {result.get('local_output_dir')}\n\n"
            f"错误: {result.get('error')}"
        )

    synced_files = result.get("synced_files", [])
    skipped_files = result.get("skipped_files", [])
    synced_summary = "\n".join(
        f"- {item['name']} ({item['size_bytes']} bytes)"
        for item in synced_files
    ) or "无"
    skipped_summary = "\n".join(
        f"- {item['name']} ({item['size_bytes']} bytes)"
        for item in skipped_files
    ) or "无"

    return (
        "VASP 输出已同步到本地。\n\n"
        f"Job ID: {job_id}\n"
        f"远端输出目录: {result['remote_output_dir']}\n"
        f"本地输出目录: {result['local_output_dir']}\n"
        f"本地原始输出目录: {result['local_raw_output_dir']}\n"
        f"本地分析目录: {result['local_analysis_dir']}\n"
        f"文件清单: {result['manifest_path']}\n\n"
        f"报告上下文: {result.get('report_context_path', '未生成')}\n"
        f"报告上下文错误: {result.get('report_context_error', '无')}\n\n"
        "已同步文件:\n"
        f"{synced_summary}\n\n"
        "已跳过文件:\n"
        f"{skipped_summary}"
    )


def _extract_vasp_report_selector(text: str):
    job_id = extract_job_id(text)

    if job_id:
        return {
            "kind": "job_id",
            "value": job_id,
        }

    absolute_match = re.search(r"(\/[^\s，,。]+)", text)

    if absolute_match:
        return {
            "kind": "path",
            "value": absolute_match.group(1),
        }

    patterns = [
        r"(?:目录名|目录|作业|job)\s*[:：=]?\s*([A-Za-z0-9_.-]+)",
        r"vasp\s*([A-Za-z0-9_.-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            value = match.group(1)

            if value.lower() not in {"报告", "report"}:
                return {
                    "kind": "name",
                    "value": value,
                }

    return None


def _path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _looks_like_vasp_input_dir(path: Path) -> bool:
    return all((path / name).is_file() for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"])


def _looks_like_vasp_output_dir(path: Path) -> bool:
    return (path / "raw_output").is_dir() or (path / "analysis" / "file_manifest.json").is_file()


def _local_output_dir_for_input_path(path: Path) -> Path:
    from modules.job_submitter import VASP_LOCAL_JOBS_DIR, VASP_LOCAL_OUTPUT_DIR

    input_root = Path(VASP_LOCAL_JOBS_DIR).expanduser()
    output_root = Path(VASP_LOCAL_OUTPUT_DIR).expanduser()

    if _path_is_relative_to(path, input_root):
        return output_root / path.name

    if _looks_like_vasp_input_dir(path):
        return output_root / path.name

    return path


def _resolve_vasp_report_job_dir(text: str):
    from modules.job_submitter import VASP_LOCAL_OUTPUT_DIR
    from modules.job_registry import get_job

    selector = _extract_vasp_report_selector(text)

    if not selector:
        return None, "请提供 Job ID、本地输出目录名或绝对路径，例如：生成 VASP 作业 si_static_test 报告。"

    if selector["kind"] == "job_id":
        job = get_job(selector["value"])

        if not job:
            return None, f"本地 registry 中没有找到 Job ID {selector['value']}。"

        if job.get("type") != "vasp":
            return None, f"Job ID {selector['value']} 不是 VASP 作业。"

        local_output_dir = job.get("local_output_dir")

        if not local_output_dir:
            return None, f"Job ID {selector['value']} 没有登记本地输出目录。"

        return Path(local_output_dir).expanduser(), None

    if selector["kind"] == "path":
        path = Path(selector["value"]).expanduser()
        output_path = _local_output_dir_for_input_path(path)

        if output_path != path:
            return output_path, None

        return path, None

    return Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / selector["value"], None


def generate_vasp_report(text: str):
    from modules.claude_code_reporter import generate_report_with_claude

    local_job_dir, error = _resolve_vasp_report_job_dir(text)

    if error:
        return error

    if not local_job_dir.is_dir():
        return (
            "没有找到本地 VASP 输出目录。\n\n"
            f"检查目录: {local_job_dir}\n\n"
            "如果你给的是本地 input 目录，请先提交并等待输出同步，"
            "或使用：分析 VASP 作业 <Job ID>。"
        )

    result = generate_report_with_claude(local_job_dir)

    return _format_vasp_report_result(result, local_job_dir)


def _format_vasp_report_result(result: dict, local_job_dir: Path) -> str:
    if not result["success"]:
        return (
            "VASP 报告生成失败。\n\n"
            f"本地输出目录: {local_job_dir}\n"
            f"报告上下文: {result.get('report_context_path')}\n"
            f"Claude Code 耗时: {result.get('elapsed_seconds', 'unknown')} 秒\n"
            f"Claude Code 超时设置: {result.get('timeout_seconds', 'unknown')} 秒\n"
            f"错误: {result.get('error')}"
        )

    return (
        "VASP 报告已生成。\n\n"
        f"本地输出目录: {result['local_job_dir']}\n"
        f"报告上下文: {result['report_context_path']}\n"
        f"用户报告: {result['report_path']}\n"
        f"论文方法: {result['paper_methods_path']}\n"
        f"论文结果: {result['paper_results_path']}\n"
        f"Claude Code 耗时: {result.get('elapsed_seconds', 'unknown')} 秒\n"
        f"Claude Code 超时设置: {result.get('timeout_seconds', 'unknown')} 秒"
    )


def analyze_vasp_job(text: str):
    from modules.claude_code_reporter import generate_report_with_claude
    from modules.job_submitter import VASP_REMOTE_OUTPUT_DIR
    from modules.slurm_tools import (
        sync_vasp_job_output as sync_by_job_id,
        sync_vasp_output_to_local,
    )

    selector = _extract_vasp_report_selector(text)

    if not selector:
        return "请提供 Job ID、本地输出目录名或绝对路径，例如：分析 VASP 作业 si_static_test。"

    sync_result = None
    local_job_dir = None

    try:
        if selector["kind"] == "job_id":
            sync_result = sync_by_job_id(selector["value"])

            if not sync_result["success"]:
                return (
                    "VASP 一键分析失败：远端输出同步失败。\n\n"
                    f"Job ID: {selector['value']}\n"
                    f"错误: {sync_result.get('error')}"
                )

            local_job_dir = Path(sync_result["local_output_dir"]).expanduser()

        elif selector["kind"] == "name":
            remote_output_dir = f"{VASP_REMOTE_OUTPUT_DIR}/{selector['value']}"
            sync_result = sync_vasp_output_to_local(remote_output_dir)
            if not sync_result["success"]:
                return (
                    "VASP 一键分析失败：远端输出同步失败。\n\n"
                    f"远端输出目录: {sync_result.get('remote_output_dir')}\n"
                    f"本地输出目录: {sync_result.get('local_output_dir')}\n"
                    f"错误: {sync_result.get('error')}"
                )
            local_job_dir = Path(sync_result["local_output_dir"]).expanduser()

        else:
            path = Path(selector["value"]).expanduser()

            if path.is_dir() and _looks_like_vasp_output_dir(path):
                local_job_dir = path
            elif path.is_dir():
                local_output_dir = _local_output_dir_for_input_path(path)

                if local_output_dir != path:
                    remote_output_dir = f"{VASP_REMOTE_OUTPUT_DIR}/{path.name}"
                    sync_result = sync_vasp_output_to_local(
                        remote_output_dir,
                        local_output_dir=local_output_dir,
                    )
                    if not sync_result["success"]:
                        return (
                            "VASP 一键分析失败：远端输出同步失败。\n\n"
                            f"远端输出目录: {sync_result.get('remote_output_dir')}\n"
                            f"本地输出目录: {sync_result.get('local_output_dir')}\n"
                            f"错误: {sync_result.get('error')}"
                        )
                    local_job_dir = Path(sync_result["local_output_dir"]).expanduser()
                else:
                    return (
                        "VASP 一键分析失败：你提供的是本地目录，但它不像已同步的 VASP 输出目录。\n\n"
                        f"检查目录: {path}\n"
                        "已同步的输出目录应包含 raw_output/ 或 analysis/file_manifest.json。\n"
                        "如果这是远端输出目录，请提供远端绝对路径；如果这是 Job ID，请直接写 Job ID。"
                    )
            else:
                sync_result = sync_vasp_output_to_local(selector["value"])
                if not sync_result["success"]:
                    return (
                        "VASP 一键分析失败：远端输出同步失败。\n\n"
                        f"远端输出目录: {sync_result.get('remote_output_dir')}\n"
                        f"本地输出目录: {sync_result.get('local_output_dir')}\n"
                        f"错误: {sync_result.get('error')}"
                    )
                local_job_dir = Path(sync_result["local_output_dir"]).expanduser()
    except Exception as error:
        return _format_remote_access_error("VASP 一键分析同步输出", error)

    if not local_job_dir or not local_job_dir.is_dir():
        return (
            "VASP 一键分析失败：没有找到本地输出目录。\n\n"
            f"检查目录: {local_job_dir}"
        )

    report_result = generate_report_with_claude(local_job_dir)
    sync_lines = []

    if sync_result:
        sync_lines = [
            "同步阶段:",
            f"- 远端输出目录: {sync_result.get('remote_output_dir')}",
            f"- 本地输出目录: {sync_result.get('local_output_dir')}",
            f"- 本地原始输出目录: {sync_result.get('local_raw_output_dir')}",
            f"- 本地分析目录: {sync_result.get('local_analysis_dir')}",
            f"- 同步文件数: {len(sync_result.get('synced_files', []))}",
            f"- 跳过文件数: {len(sync_result.get('skipped_files', []))}",
            "",
        ]

    title = "VASP 一键分析完成。" if report_result["success"] else "VASP 一键分析未完成：同步成功，但报告生成失败。"

    return (
        f"{title}\n\n"
        + "\n".join(sync_lines)
        + _format_vasp_report_result(report_result, local_job_dir)
    )
