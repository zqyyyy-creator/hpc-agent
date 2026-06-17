import shlex

from modules.core.hpc_config import (
    REMOTE_WORKDIR,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
)
from modules.slurm.remote import run_remote_command


def list_remote_agent_jobs():
    command = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        "find . -maxdepth 3 -type f "
        "\\( -name '*.out' -o -name '*.err' -o -name 'job.sh' \\) "
        "-printf '%P\\n' | sort"
    )

    output, error = run_remote_command(command)

    return {
        "remote_workdir": REMOTE_WORKDIR,
        "output": output,
        "error": error,
    }


def list_remote_vasp_jobs():
    roots = [
        ("input", VASP_REMOTE_INPUT_DIR),
        ("output", VASP_REMOTE_OUTPUT_DIR),
    ]
    outputs = []
    errors = []

    for label, root_dir in roots:
        if not root_dir:
            errors.append(f"{label}: 未配置远端 VASP {label} 目录。")
            continue

        command = (
            f"cd {shlex.quote(root_dir)} && "
            "find . -mindepth 1 -maxdepth 1 "
            "-printf '%y\\t%P\\n' | sort"
        )
        output, error = run_remote_command(command)
        outputs.append(f"## {label}\nroot\t{root_dir}\n{output.rstrip()}")

        if error.strip():
            errors.append(f"{label}: {error.rstrip()}")

    return {
        "remote_input_dir": VASP_REMOTE_INPUT_DIR,
        "remote_output_dir": VASP_REMOTE_OUTPUT_DIR,
        "output": "\n\n".join(outputs).strip(),
        "error": "\n".join(errors),
    }
