import re


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

    result = list_remote_agent_jobs()

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


def _format_cleanup_targets(targets):
    if not targets:
        return "无"

    return "\n".join(
        f"- {target['kind']}: {target['path']}"
        for target in targets
    )


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


def execute_cleanup_remote_jobs(targets):
    from modules.slurm_tools import cleanup_remote_agent_targets

    result = cleanup_remote_agent_targets(targets)
    deleted = _format_cleanup_targets(result.get("deleted", []))

    if result["success"]:
        return (
            "远端普通作业文件已清理。\n\n"
            f"远端根目录: {result['remote_workdir']}\n\n"
            "已删除:\n"
            f"{deleted}"
        )

    return (
        "远端普通作业文件清理失败。\n\n"
        f"远端根目录: {result['remote_workdir']}\n\n"
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
