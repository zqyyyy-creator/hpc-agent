from tests import _bootstrap  # noqa: F401

from modules.core.environment_status import (
    check_hpc_environment,
    format_hpc_environment_check,
    format_current_model_and_config,
)


def test_current_model_config_masks_api_key():
    text = format_current_model_and_config()

    assert "Agent 主体模型" in text
    assert "Claude Code VASP 报告模型" in text
    assert "API Key:" in text
    assert "sk-" not in text


def test_hpc_environment_check_uses_injected_remote_runner():
    def fake_run_remote_command(command):
        return "\n".join([
            "DIR\t/remote/home/testuser/hpc-agent-jobs\tyes\tyes",
            "DIR\t/remote/home/testuser/vasp-hpc-jobs-input\tyes\tyes",
            "DIR\t/remote/home/testuser/vasp-hpc-jobs-output\tyes\tyes",
        ]), ""

    result = check_hpc_environment(run_remote_command=fake_run_remote_command)
    text = format_hpc_environment_check(result)

    assert "超算配置体检" in text
    assert "HPC_HOST" in text
    assert "HPC_REMOTE_WORKDIR" in text


if __name__ == "__main__":
    test_current_model_config_masks_api_key()
    test_hpc_environment_check_uses_injected_remote_runner()
    print("All environment status checks passed.")
