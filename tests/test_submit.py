import _bootstrap

from modules.slurm_tools import submit_job


LAST_JOB_FILE = _bootstrap.PROJECT_ROOT / ".last_job_id"
SCRIPT_PATH = _bootstrap.PROJECT_ROOT / "job.sh"

result = submit_job(SCRIPT_PATH)

print("SUCCESS:")
print(result["success"])

print("JOB ID:")
print(result["job_id"])

print("OUTPUT:")
print(result["output"])

print("ERROR:")
print(result["error"])

if not result["success"]:
    raise SystemExit("作业提交失败，请检查 ERROR 输出。")

if not result["job_id"]:
    raise SystemExit("作业可能已提交，但没有解析到 job_id，请检查 OUTPUT 输出。")

LAST_JOB_FILE.write_text(result["job_id"], encoding="utf-8")

print("LAST JOB FILE:")
print(LAST_JOB_FILE)
