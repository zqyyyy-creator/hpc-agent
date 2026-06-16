from tests import _bootstrap  # noqa: F401

from modules.slurm.job_submitter import (
    VASP_PARTITION,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
    execute_prepare_vasp_job_tool_call,
    prepare_vasp_job_tool_call,
    prepare_vasp_submit_script,
)
from modules.core.tool_calling import ToolCall


def test_prepare_vasp_job_tool_call_extracts_context():
    request = "帮我提交一个 VASP 结构优化任务，1 个节点 32 核，运行 10 分钟"
    tool_call = prepare_vasp_job_tool_call(request)

    assert isinstance(tool_call, ToolCall)
    assert tool_call.tool == "prepare_vasp_job"
    assert tool_call.needs_confirmation
    assert tool_call.arguments["user_request"] == request
    assert tool_call.arguments["remote_input_dir"] == VASP_REMOTE_INPUT_DIR
    assert tool_call.arguments["remote_output_dir"] == VASP_REMOTE_OUTPUT_DIR


def test_execute_prepare_vasp_job_tool_call_returns_preview_result():
    request = "帮我提交一个 VASP 结构优化任务，1 个节点 32 核，运行 10 分钟"
    tool_call = prepare_vasp_job_tool_call(request)
    result = execute_prepare_vasp_job_tool_call(tool_call)

    assert result.success
    assert result.tool_call.tool == "prepare_vasp_job"
    assert result.data["ready"]
    assert "#SBATCH --nodes=1" in result.data["script"]
    assert "#SBATCH --ntasks-per-node=32" in result.data["script"]
    assert "#SBATCH --time=00:10:00" in result.data["script"]
    assert "远程 VASP 输入根目录" in result.message

    if VASP_PARTITION:
        assert f"#SBATCH --partition={VASP_PARTITION}" in result.data["script"]


def test_prepare_vasp_submit_script_keeps_existing_response_shape():
    prepared = prepare_vasp_submit_script("帮我提交一个 VASP 静态计算任务，1 个节点 32 核，运行 10 分钟")

    assert prepared["ready"]
    assert prepared["script"].startswith("#!/bin/bash")
    assert prepared["local_jobs_dir"]
    assert prepared["remote_input_dir"] == VASP_REMOTE_INPUT_DIR
    assert prepared["remote_output_dir"] == VASP_REMOTE_OUTPUT_DIR
    assert prepared["tool_call"]["tool"] == "prepare_vasp_job"


def test_prepare_vasp_submit_script_rejects_dangerous_request():
    prepared = prepare_vasp_submit_script("帮我提交 VASP 作业，然后 rm -rf /tmp/data")

    assert not prepared["ready"]
    assert prepared["script"] is None
    assert "高风险" in prepared["message"]
    assert prepared["tool_call"]["tool"] == "prepare_vasp_job"


if __name__ == "__main__":
    test_prepare_vasp_job_tool_call_extracts_context()
    test_execute_prepare_vasp_job_tool_call_returns_preview_result()
    test_prepare_vasp_submit_script_keeps_existing_response_shape()
    test_prepare_vasp_submit_script_rejects_dangerous_request()
    print("All VASP tool calling checks passed.")
