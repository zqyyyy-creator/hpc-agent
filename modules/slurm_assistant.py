import re
from pathlib import Path


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


def has_cpu_count(text: str) -> bool:
    return bool(re.search(r"(\d+)\s*(核|cpu|CPU|core|cores)", text))


def extract_time_limit(text: str) -> str:
    match = re.search(r"\b(\d{1,2}:\d{2}:\d{2})\b", text)
    if match:
        return match.group(1)

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


def has_time_limit(text: str) -> bool:
    return bool(
        re.search(r"\b(\d{1,2}:\d{2}:\d{2})\b", text)
        or re.search(r"(\d+)\s*(分钟|minute|minutes|min)", text)
        or re.search(r"(\d+)\s*(小时|hour|hours|hr)", text)
    )


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


def has_memory(text: str) -> bool:
    return extract_memory(text) is not None


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


def has_gpu_count(text: str) -> bool:
    return bool(
        re.search(r"gpu\s*[:=]\s*(\d+)", text, re.IGNORECASE)
        or re.search(r"(\d+)\s*(张\s*)?(gpu|GPU|卡)", text)
        or re.search(r"\bgpu\b|GPU", text)
    )


def recommend_resources_for_file(file_name: str, file_content: bytes | str):
    if isinstance(file_content, bytes):
        text = file_content.decode("utf-8", errors="ignore")
    else:
        text = file_content

    lower_name = file_name.lower()
    lower_text = text.lower()
    recommendations = {}
    reasons = []

    if lower_name.endswith(".sh"):
        recommendations.update({"cpus": 1, "time": "00:10:00"})
        reasons.append("Shell 脚本默认按轻量作业处理。")
    else:
        recommendations.update({"cpus": 2, "time": "00:30:00", "memory": "4G"})
        reasons.append("Python 脚本默认按普通计算作业处理。")

    if any(token in lower_text for token in ["torch", "tensorflow", "keras", "jax"]):
        recommendations.update({"cpus": 4, "time": "02:00:00", "memory": "16G"})
        reasons.append("检测到深度学习框架，建议增加 CPU、内存和运行时间。")

    if any(token in lower_text for token in ["cuda", ".to('cuda'", '.to("cuda"', "cudnn"]):
        recommendations["gpu"] = 1
        reasons.append("检测到 CUDA/GPU 相关代码，建议申请 1 张 GPU。")

    if any(token in lower_text for token in ["mpi4py", "mpirun", "srun"]):
        recommendations["cpus"] = max(recommendations.get("cpus", 1), 8)
        recommendations["time"] = "01:00:00"
        reasons.append("检测到 MPI/SRUN 相关代码，建议提高 CPU 数。")

    if re.search(r"for\s+\w+\s+in\s+range\((?:\d{3,}|epochs?|steps?)", lower_text):
        recommendations["time"] = "01:00:00"
        reasons.append("检测到较长循环，建议预留更长运行时间。")

    if "time.sleep" in lower_text:
        recommendations["time"] = "00:30:00"
        reasons.append("检测到 sleep/监控测试代码，建议预留 30 分钟。")

    if any(token in lower_text for token in ["pandas", "numpy", "scipy", "sklearn"]):
        recommendations["memory"] = max_memory(recommendations.get("memory"), "8G")
        reasons.append("检测到常见数据/科学计算库，建议至少 8G 内存。")

    return {
        "cpus": recommendations.get("cpus"),
        "time": recommendations.get("time"),
        "memory": recommendations.get("memory"),
        "gpu": recommendations.get("gpu"),
        "reasons": reasons,
    }


def max_memory(current: str | None, candidate: str):
    if not current:
        return candidate

    def to_mb(value: str):
        match = re.match(r"(\d+)\s*([gm])", value.lower())
        if not match:
            return 0
        amount = int(match.group(1))
        return amount * 1024 if match.group(2) == "g" else amount

    return candidate if to_mb(candidate) > to_mb(current) else current


def build_resource_recommendation_text(user_request: str, uploaded_files):
    if not uploaded_files:
        return "", []

    recommendation = recommend_resources_for_file(
        uploaded_files[0]["name"],
        uploaded_files[0]["content"],
    )
    additions = []
    applied = []

    if recommendation.get("cpus") and not has_cpu_count(user_request):
        additions.append(f"{recommendation['cpus']}核")
        applied.append(f"CPU: {recommendation['cpus']} 核")

    if recommendation.get("time") and not has_time_limit(user_request):
        additions.append(f"运行时间 {recommendation['time']}")
        applied.append(f"时间: {recommendation['time']}")

    if recommendation.get("memory") and not has_memory(user_request):
        additions.append(f"{recommendation['memory']}内存")
        applied.append(f"内存: {recommendation['memory']}")

    if recommendation.get("gpu") and not has_gpu_count(user_request):
        additions.append(f"{recommendation['gpu']}张GPU")
        applied.append(f"GPU: {recommendation['gpu']}")

    if not additions:
        return "", []

    note = "推荐资源: " + "，".join(additions)
    reasons = recommendation.get("reasons", [])
    return note, applied + [f"原因: {reason}" for reason in reasons]


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

    match = re.search(r"(?:跑|运行|执行|提交|run|submit)\s*([A-Za-z0-9_./-]+\.py)", text, re.IGNORECASE)
    if match:
        return f"python {Path(match.group(1)).name}"

    match = re.search(r"(?:跑|运行|执行|提交|run|submit)\s*([A-Za-z0-9_./-]+\.sh)", text, re.IGNORECASE)
    if match:
        return f"bash {Path(match.group(1)).name}"

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
