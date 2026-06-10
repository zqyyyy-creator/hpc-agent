import os
import re
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_VASP_JOB_NAME = "vasp_job"
DEFAULT_VASP_NODES = 1
DEFAULT_VASP_TASKS_PER_NODE = 32
DEFAULT_VASP_TIME_LIMIT = "24:00:00"
DEFAULT_VASP_OUTPUT_FILE = "%x_%j.out"
DEFAULT_VASP_ERROR_FILE = "%x_%j.err"
DEFAULT_VASP_SETUP_COMMAND = os.getenv(
    "HPC_VASP_SETUP_COMMAND",
    "source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/linux/bin/compilervars.sh intel64",
)
DEFAULT_VASP_COMMAND = os.getenv("HPC_VASP_COMMAND", "mpirun /public1/soft/vasp")
DEFAULT_VASP_MODULE = os.getenv("HPC_VASP_MODULE", "")

DANGEROUS_COMMAND_PATTERNS = [
    r"\brm\s+-[^\n;]*r[^\n;]*f\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bmkfs\b",
    r">\s*/etc/",
]

VASP_INPUT_FILES = ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]


def extract_vasp_job_name(text: str) -> str:
    match = re.search(r"(?:job[-_ ]?name|作业名|任务名)\s*[:：=]?\s*([A-Za-z0-9_.-]+)", text)
    if match:
        return match.group(1)

    if "结构优化" in text:
        return "vasp_relax"

    if "静态" in text or "static" in text.lower():
        return "vasp_static"

    return DEFAULT_VASP_JOB_NAME


def extract_vasp_nodes(text: str) -> int:
    match = re.search(r"(\d+)\s*(个)?\s*(节点|node|nodes)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return DEFAULT_VASP_NODES


def extract_vasp_tasks_per_node(text: str) -> int:
    match = re.search(
        r"(?:每(?:个)?节点|per[-_ ]?node).*?(\d+)\s*(核|进程|任务|core|cores|task|tasks)",
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)\s*(核|进程|任务|cpu|CPU|core|cores)", text)
    if match:
        return int(match.group(1))

    return DEFAULT_VASP_TASKS_PER_NODE


def extract_vasp_time_limit(text: str) -> str:
    day_match = re.search(r"(\d+)\s*(天|day|days)", text, re.IGNORECASE)
    hour_match = re.search(r"(\d+)\s*(小时|hour|hours|hr|h)", text, re.IGNORECASE)
    minute_match = re.search(r"(\d+)\s*(分钟|minute|minutes|min)", text, re.IGNORECASE)

    if day_match:
        days = int(day_match.group(1))
        return f"{days}-00:00:00"

    if hour_match:
        hours = int(hour_match.group(1))
        return f"{hours:02d}:00:00"

    if minute_match:
        minutes = int(minute_match.group(1))
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}:00"

    return DEFAULT_VASP_TIME_LIMIT


def extract_vasp_command(text: str) -> str:
    command_patterns = [
        r"((?:srun|mpirun|mpiexec)(?:\s+-[A-Za-z0-9_.=-]+(?:\s+\d+)?)?\s+/[^\s;|&]*vasp[^\s;|&]*)",
        r"((?:srun|mpirun|mpiexec)(?:\s+-[A-Za-z0-9_.=-]+(?:\s+\d+)?)?\s+vasp_(?:std|gam|ncl))",
        r"\b(/[^\s;|&]*vasp[^\s;|&]*)\b",
        r"\b(vasp_(?:std|gam|ncl))\b",
    ]

    for pattern in command_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return DEFAULT_VASP_COMMAND


def is_dangerous_command(command: str) -> bool:
    return any(
        re.search(pattern, command, re.IGNORECASE)
        for pattern in DANGEROUS_COMMAND_PATTERNS
    )


def generate_vasp_sbatch_script(user_request: str) -> str:
    if is_dangerous_command(user_request):
        return "这个 VASP 请求包含高风险命令，我不能为它生成 sbatch 脚本。请提供安全的运行命令。"

    job_name = extract_vasp_job_name(user_request)
    nodes = extract_vasp_nodes(user_request)
    tasks_per_node = extract_vasp_tasks_per_node(user_request)
    time_limit = extract_vasp_time_limit(user_request)
    command = extract_vasp_command(user_request)

    if is_dangerous_command(command):
        return "这个 VASP 运行命令风险过高，我不能为它生成 sbatch 脚本。请提供安全的运行命令。"

    directives = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --nodes={nodes}",
        f"#SBATCH --ntasks-per-node={tasks_per_node}",
        f"#SBATCH --time={time_limit}",
        f"#SBATCH --output={DEFAULT_VASP_OUTPUT_FILE}",
        f"#SBATCH --error={DEFAULT_VASP_ERROR_FILE}",
    ]

    setup_lines = []
    if DEFAULT_VASP_SETUP_COMMAND:
        setup_lines.append(DEFAULT_VASP_SETUP_COMMAND)
    if DEFAULT_VASP_MODULE:
        setup_lines.append(f"module load {DEFAULT_VASP_MODULE}")

    input_checks = "\n".join([
        f'test -f {name} || {{ echo "Missing required VASP input file: {name}"; exit 1; }}'
        for name in VASP_INPUT_FILES
    ])

    body = "\n".join([
        "",
        "# Check required VASP input files before starting the calculation.",
        input_checks,
        "",
        *setup_lines,
        "",
        f"{command} > vasp.out",
        "",
    ])

    return "\n".join(directives) + body


def prepare_vasp_submit_script(user_request: str):
    script = generate_vasp_sbatch_script(user_request)

    if not script.startswith("#!/bin/bash"):
        return {
            "ready": False,
            "script": None,
            "message": script,
        }

    return {
        "ready": True,
        "script": script,
        "message": (
            "我将生成下面的 VASP 作业脚本。请确认远程运行目录中已经包含 "
            "INCAR、POSCAR、POTCAR、KPOINTS。\n\n"
            f"{script}\n请确认后再提交。"
        ),
    }
