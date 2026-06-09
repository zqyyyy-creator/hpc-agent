import os
from pathlib import Path

from dotenv import load_dotenv

from modules.slurm_assistant import generate_sbatch_script


load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_PARTITION = os.getenv("HPC_DEFAULT_PARTITION", "amd_test")


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


def submit_prepared_script(script: str):
    from modules.slurm_tools import submit_script_text

    result = submit_script_text(script)

    if result["success"] and result["job_id"]:
        return {
            "success": True,
            "job_id": result["job_id"],
            "answer": (
                "作业已提交成功。\n\n"
                f"Job ID: {result['job_id']}\n"
                f"远程脚本: {result['remote_script']}\n\n"
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
