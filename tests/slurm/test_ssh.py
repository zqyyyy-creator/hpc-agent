from tests import _bootstrap  # noqa: F401

from modules.slurm.slurm_tools import run_remote_command


output, error = run_remote_command("hostname && pwd && squeue -u $USER")

print("STDOUT:")
print(output)

print("STDERR:")
print(error)

if error.strip():
    raise SystemExit("SSH 测试命令返回错误，请检查 STDERR。")
