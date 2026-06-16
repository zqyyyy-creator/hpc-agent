import time
from pathlib import Path

from tests import _bootstrap

from modules.slurm.job_submitter import prepare_submit_script, submit_prepared_script
from modules.slurm.slurm_tools import (
    check_job,
    read_job_error,
    read_job_output,
)


LAST_JOB_FILE = _bootstrap.PROJECT_ROOT / ".last_job_id"
POLL_SECONDS = 5
MAX_POLLS = 12


def print_section(title, value):
    print("=" * 60)
    print(title)
    print("=" * 60)
    print(value)


def main():
    prepared = prepare_submit_script(
        "帮我提交一个作业运行 bash live_hpc_check.sh，1 核，1 分钟"
    )

    if not prepared["ready"]:
        raise SystemExit(f"无法生成 live HPC 测试脚本：{prepared['message']}")

    submit_result = submit_prepared_script(
        prepared["script"],
        uploaded_files=[
            {
                "name": "live_hpc_check.sh",
                "content": (
                    "#!/bin/bash\n"
                    "echo HPC_AGENT_LIVE_OK\n"
                    "hostname\n"
                    "date\n"
                ).encode("utf-8"),
            }
        ],
    )

    print_section("SUBMIT RESULT", submit_result)

    if not submit_result["success"]:
        raise SystemExit("作业提交失败，请检查 SUBMIT RESULT 中的 error。")

    job_id = submit_result["job_id"]

    if not job_id:
        raise SystemExit("作业可能已提交，但没有解析到 job_id。")

    LAST_JOB_FILE.write_text(job_id, encoding="utf-8")
    print_section("JOB ID", job_id)

    last_queue_result = None
    job_left_queue = False

    for index in range(MAX_POLLS):
        last_queue_result = check_job(job_id)
        print_section(f"QUEUE CHECK {index + 1}/{MAX_POLLS}", last_queue_result)

        queue_output = last_queue_result["output"].strip()
        queue_lines = [
            line
            for line in queue_output.splitlines()
            if line.strip()
        ]

        if len(queue_lines) <= 1:
            job_left_queue = True
            break

        time.sleep(POLL_SECONDS)

    if not job_left_queue:
        print_section(
            "WORKFLOW",
            (
                "Job submitted successfully, but it is still in the queue. "
                "Run python3 tests/slurm/test_tools.py later to read status and logs."
            ),
        )
        return

    output_result = read_job_output(job_id)
    error_result = read_job_error(job_id)

    print_section("JOB STDOUT", output_result)
    print_section("JOB STDERR", error_result)

    if output_result["error"].strip():
        raise SystemExit("读取 stdout 失败，请检查 JOB STDOUT 中的 error。")

    if error_result["error"].strip():
        raise SystemExit("读取 stderr 失败，请检查 JOB STDERR 中的 error。")

    print_section("WORKFLOW", "HPC workflow check passed.")


if __name__ == "__main__":
    main()
