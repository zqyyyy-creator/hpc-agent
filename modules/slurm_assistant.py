import re


DEFAULT_JOB_NAME = "hpc_agent_job"
DEFAULT_TIME_LIMIT = "00:10:00"
DEFAULT_OUTPUT_FILE = "%x_%j.out"
DEFAULT_ERROR_FILE = "%x_%j.err"

DANGEROUS_COMMAND_PATTERNS = [
    r"\brm\s+-[^\n;]*r[^\n;]*f\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r">\s*/etc/",
]


def extract_cpu_count(text: str) -> int:
    match = re.search(r"(\d+)\s*(核|cpu|CPU|core|cores)", text)
    if match:
        return int(match.group(1))
    return 1


def extract_time_limit(text: str) -> str:
    match = re.search(r"(\d+)\s*(分钟|minute|minutes|min)", text)
    if match:
        minutes = int(match.group(1))
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}:00"

    match = re.search(r"(\d+)\s*(小时|hour|hours|hr)", text)
    if match:
        hours = int(match.group(1))
        return f"{hours:02d}:00:00"

    return DEFAULT_TIME_LIMIT


def extract_memory(text: str):
    match = re.search(r"(\d+)\s*(gb|g|GB|G|吉)\b", text)
    if match:
        return f"{match.group(1)}G"

    match = re.search(r"(\d+)\s*GB?\s*内存", text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}G"

    match = re.search(r"(\d+)\s*内存", text)
    if match:
        return f"{match.group(1)}G"

    match = re.search(r"(\d+)\s*(mb|MB|m|M)", text)
    if match:
        return f"{match.group(1)}M"

    return None


def extract_gpu_count(text: str):
    match = re.search(r"gpu\s*[:=]\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*(张\s*)?(gpu|GPU|卡)", text)
    if match:
        return int(match.group(1))

    if re.search(r"\bgpu\b|GPU", text):
        return 1

    return None


def extract_job_name(text: str) -> str:
    match = re.search(r"(?:job[-_ ]?name|作业名|任务名)\s*[:：=]?\s*([A-Za-z0-9_.-]+)", text)
    if match:
        return match.group(1)

    return DEFAULT_JOB_NAME


def extract_command(text: str):
    match = re.search(r"(python\s+\S+\.py)", text)
    if match:
        return match.group(1)

    match = re.search(r"(bash\s+\S+\.sh)", text)
    if match:
        return match.group(1)

    match = re.search(r"(\./[A-Za-z0-9_./-]+)", text)
    if match:
        return match.group(1)

    return None


def is_dangerous_command(command: str) -> bool:
    return any(
        re.search(pattern, command, re.IGNORECASE)
        for pattern in DANGEROUS_COMMAND_PATTERNS
    )


def generate_sbatch_script(user_request: str) -> str:
    if is_dangerous_command(user_request):
        return "这个命令风险过高，我不能为它生成 sbatch 脚本。请提供安全的运行命令。"

    job_name = extract_job_name(user_request)
    cpus = extract_cpu_count(user_request)
    memory = extract_memory(user_request)
    time_limit = extract_time_limit(user_request)
    gpu_count = extract_gpu_count(user_request)
    command = extract_command(user_request)

    if not command:
        return "请告诉我要运行的命令，例如：python train.py 或 bash run.sh。"

    if is_dangerous_command(command):
        return "这个命令风险过高，我不能为它生成 sbatch 脚本。请提供安全的运行命令。"

    directives = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --cpus-per-task={cpus}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --output={DEFAULT_OUTPUT_FILE}",
        f"#SBATCH --error={DEFAULT_ERROR_FILE}",
    ]

    if memory:
        directives.append(f"#SBATCH --mem={memory}")

    if gpu_count:
        directives.append(f"#SBATCH --gres=gpu:{gpu_count}")

    return "\n".join(directives) + f"""

{command}
"""


def suggest_slurm_parameters(user_request: str) -> str:
    cpus = extract_cpu_count(user_request)
    memory = extract_memory(user_request)
    time_limit = extract_time_limit(user_request)
    gpu_count = extract_gpu_count(user_request)

    directives = [
        "建议使用以下 Slurm 参数：",
        "",
        f"#SBATCH --cpus-per-task={cpus}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --output={DEFAULT_OUTPUT_FILE}",
        f"#SBATCH --error={DEFAULT_ERROR_FILE}",
    ]

    if memory:
        directives.append(f"#SBATCH --mem={memory}")

    if gpu_count:
        directives.append(f"#SBATCH --gres=gpu:{gpu_count}")

    return "\n".join(directives) + "\n"
