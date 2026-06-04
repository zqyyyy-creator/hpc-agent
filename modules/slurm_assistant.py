import re


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

    return "01:00:00"


def extract_command(text: str) -> str:
    match = re.search(r"(python\s+\S+\.py)", text)
    if match:
        return match.group(1)

    match = re.search(r"(bash\s+\S+\.sh)", text)
    if match:
        return match.group(1)

    return "python main.py"


def generate_sbatch_script(user_request: str) -> str:
    cpus = extract_cpu_count(user_request)
    time_limit = extract_time_limit(user_request)
    command = extract_command(user_request)

    return f"""#!/bin/bash
#SBATCH --job-name=hpc_job
#SBATCH --cpus-per-task={cpus}
#SBATCH --time={time_limit}
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err

{command}
"""


def suggest_slurm_parameters(user_request: str) -> str:
    cpus = extract_cpu_count(user_request)
    time_limit = extract_time_limit(user_request)

    return f"""建议使用以下 Slurm 参数：

#SBATCH --cpus-per-task={cpus}
#SBATCH --time={time_limit}
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
"""