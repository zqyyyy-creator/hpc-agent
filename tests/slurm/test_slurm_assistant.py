from tests import _bootstrap  # noqa: F401

from modules.routing.router import detect_intent
from modules.slurm.slurm_assistant import generate_sbatch_script


def assert_contains(text: str, expected: str):
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in:\n{text}")


def assert_not_contains(text: str, unexpected: str):
    if unexpected in text:
        raise AssertionError(f"Did not expect to find {unexpected!r} in:\n{text}")


def test_basic_python_script():
    request = "帮我生成一个 4 核、运行 10 分钟的 Python 作业脚本，运行 python train.py"
    script = generate_sbatch_script(request)

    assert detect_intent(request) == "generate_sbatch"
    assert_contains(script, "#SBATCH --job-name=hpc_agent_job")
    assert_contains(script, "#SBATCH --cpus-per-task=4")
    assert_contains(script, "#SBATCH --time=00:10:00")
    assert_contains(script, "#SBATCH --output=%x_%j.out")
    assert_contains(script, "#SBATCH --error=%x_%j.err")
    assert_contains(script, "python train.py")


def test_gpu_python_script():
    request = "Create an sbatch script to run python train.py on 1 GPU for 2 hours"
    script = generate_sbatch_script(request)

    assert detect_intent(request) == "generate_sbatch"
    assert_contains(script, "#SBATCH --gres=gpu:1")
    assert_contains(script, "#SBATCH --time=02:00:00")
    assert_contains(script, "python train.py")
    assert_not_contains(script, "#SBATCH --mem=1G")


def test_memory_shell_script():
    request = "帮我生成一个需要 8GB 内存的作业脚本，运行 bash run.sh"
    script = generate_sbatch_script(request)

    assert detect_intent(request) == "generate_sbatch"
    assert_contains(script, "#SBATCH --mem=8G")
    assert_contains(script, "bash run.sh")


def test_missing_command_still_generates():
    """Vague sbatch requests now fall back to LLM generation instead of asking."""
    request = "帮我生成一个 sbatch 脚本"
    answer = generate_sbatch_script(request)

    assert detect_intent(request) == "generate_sbatch"
    assert_contains(answer, "#!/bin/bash")


def test_hpc_submission_smoke_test_generates_hostname_script():
    answer = generate_sbatch_script("一键测试超算提交流程", allow_llm_fallback=False)

    assert_contains(answer, "#!/bin/bash")
    assert_contains(answer, "#SBATCH --job-name=hpc_agent_smoke_test")
    assert_contains(answer, "hostname")
    assert_not_contains(answer, "请告诉我要运行的命令")


def test_dangerous_command_is_rejected():
    request = "帮我生成脚本运行 rm -rf /tmp/data"
    answer = generate_sbatch_script(request)

    assert detect_intent(request) == "generate_sbatch"
    assert_contains(answer, "风险过高")


def test_resource_question_is_not_treated_as_submission():
    assert detect_intent("提交作业怎么申请资源，需要多少核") == "rag_qa"


if __name__ == "__main__":
    test_basic_python_script()
    test_gpu_python_script()
    test_memory_shell_script()
    test_missing_command_still_generates()
    test_hpc_submission_smoke_test_generates_hostname_script()
    test_dangerous_command_is_rejected()
    test_resource_question_is_not_treated_as_submission()
    print("All slurm assistant skill checks passed.")
