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
