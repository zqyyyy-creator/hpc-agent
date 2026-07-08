from tests import _bootstrap  # noqa: F401

from modules.core.environment_status import (
    build_config_recovery_suggestions,
    check_hpc_environment,
    format_hpc_environment_check,
    format_current_model_and_config,
)


def test_current_model_config_masks_api_key():
    text = format_current_model_and_config()

    assert "Agent 主体模型" in text
    assert "VASP 报告模型" in text
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


def test_environment_recovery_suggestions_cover_common_config_errors():
    result = {
        "success": False,
        "checks": [
            {"ok": False, "label": "HPC_HOST", "detail": "未配置", "code": "required_env", "metadata": {}},
            {"ok": False, "label": "HPC_KEY_PATH", "detail": "/tmp/missing-key (不存在)", "code": "ssh_key", "metadata": {"path": "/tmp/missing-key"}},
            {"ok": False, "label": "HPC_LOCAL_WORKDIR", "detail": "/tmp/hpc-missing (不存在)", "code": "local_dir", "metadata": {"path": "/tmp/hpc-missing"}},
            {"ok": False, "label": "HPC_REMOTE_WORKDIR", "detail": "/remote/work (exists=False, writable=False)", "code": "remote_dir", "metadata": {"path": "/remote/work"}},
            {"ok": False, "label": "HPC_VASP_REMOTE_INPUT_DIR", "detail": "/remote/vasp-input (exists=False, writable=False)", "code": "remote_dir", "metadata": {"path": "/remote/vasp-input"}},
            {"ok": False, "label": "HPC_VASP_REMOTE_OUTPUT_DIR", "detail": "/remote/vasp-output (exists=True, writable=False)", "code": "remote_dir", "metadata": {"path": "/remote/vasp-output"}},
            {"ok": False, "label": "HPC_VASP_COMMAND", "detail": "cmd=mpirun /bad/vasp first=mpirun first_ok=yes abs=/bad/vasp abs_ok=no", "code": "vasp_command", "metadata": {"command": "mpirun /bad/vasp"}},
            {"ok": False, "label": "HPC_VASP_SETUP_COMMAND", "detail": "setup_ok=yes mpirun_ok=no", "code": "vasp_setup", "metadata": {"command": "source /bad/env.sh"}},
            {"ok": False, "label": "partition:bad_part", "detail": "bad_part not found or not available", "code": "partition", "metadata": {"partition": "bad_part"}},
            {"ok": False, "label": "PARATERA_API_KEY", "detail": "<未配置>", "code": "api_config", "metadata": {}},
            {"ok": False, "label": "HPC_CLAUDE_CODE_COMMAND", "detail": "claude 不在 PATH 中", "code": "claude_code", "metadata": {"command": "claude"}},
        ],
        "remote_error": "",
    }

    suggestions = build_config_recovery_suggestions(result)
    text = format_hpc_environment_check({**result, "recovery_suggestions": suggestions})

    assert "补齐 HPC_HOST" in text
    assert "修复 SSH 私钥配置" in text
    assert "创建或修复本地目录 HPC_LOCAL_WORKDIR" in text
    assert "创建或修复远端目录 HPC_REMOTE_WORKDIR" in text
    assert "创建或修复远端目录 HPC_VASP_REMOTE_INPUT_DIR" in text
    assert "创建或修复远端目录 HPC_VASP_REMOTE_OUTPUT_DIR" in text
    assert "修复 HPC_VASP_COMMAND" in text
    assert "修复 HPC_VASP_SETUP_COMMAND" in text
    assert "检查 partition bad_part" in text
    assert "检查 Claude/API 配置 PARATERA_API_KEY" in text
    assert "修复 Claude Code 命令" in text


if __name__ == "__main__":
    test_current_model_config_masks_api_key()
    test_hpc_environment_check_uses_injected_remote_runner()
    test_environment_recovery_suggestions_cover_common_config_errors()
    print("All environment status checks passed.")
