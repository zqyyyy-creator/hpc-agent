from modules.slurm_tools import submit_job


LAST_JOB_FILE = ".last_job_id"

result = submit_job("job.sh")

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

with open(LAST_JOB_FILE, "w", encoding="utf-8") as f:
    f.write(result["job_id"])

print("LAST JOB FILE:")
print(LAST_JOB_FILE)
