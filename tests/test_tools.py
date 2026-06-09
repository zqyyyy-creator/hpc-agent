import sys
from pathlib import Path

import _bootstrap

from modules.slurm_tools import (
    check_job,
    read_job_output,
    read_job_error,
)

LAST_JOB_FILE = _bootstrap.PROJECT_ROOT / ".last_job_id"


def get_job_id():
    if len(sys.argv) > 1:
        return sys.argv[1]

    if LAST_JOB_FILE.exists():
        return LAST_JOB_FILE.read_text(encoding="utf-8").strip()

    raise SystemExit("请提供 job_id，或先运行 python3 test_submit.py 生成 .last_job_id。")


job_id = get_job_id()

print("JOB ID:")
print(job_id)

print("QUEUE:")
print(check_job(job_id))

print("OUTPUT:")
print(read_job_output(job_id))

print("ERROR:")
print(read_job_error(job_id))
