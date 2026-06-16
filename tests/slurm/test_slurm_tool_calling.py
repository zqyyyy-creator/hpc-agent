from tests import _bootstrap  # noqa: F401

from modules.slurm.job_submitter import (
    DEFAULT_PARTITION,
    execute_prepare_slurm_job_tool_call,
    prepare_slurm_job_tool_call,
    prepare_submit_script,
)
from modules.core.tool_calling import ToolCall


def test_prepare_slurm_job_tool_call_extracts_arguments():
    request = "帮我提交一个作业运行 python train.py，4 核，10 分钟，8G内存"
    tool_call = prepare_slurm_job_tool_call(request)

    assert isinstance(tool_call, ToolCall)
    assert tool_call.tool == "prepare_slurm_job"
    assert tool_call.needs_confirmation
    assert tool_call.arguments["command"] == "python train.py"
    assert tool_call.arguments["cpus"] == 4
    assert tool_call.arguments["time"] == "00:10:00"
    assert tool_call.arguments["memory"] == "8G"


def test_execute_prepare_slurm_job_tool_call_returns_preview_result():
    request = "帮我提交一个作业运行 python train.py，4 核，10 分钟"
    tool_call = prepare_slurm_job_tool_call(request)
    result = execute_prepare_slurm_job_tool_call(tool_call)

    assert result.success
    assert result.tool_call.tool == "prepare_slurm_job"
    assert result.data["ready"]
    assert "#SBATCH --cpus-per-task=4" in result.data["script"]
    assert "#SBATCH --time=00:10:00" in result.data["script"]
    assert "python train.py" in result.data["script"]
    assert "请确认后再提交" in result.message

    if DEFAULT_PARTITION:
        assert f"#SBATCH --partition={DEFAULT_PARTITION}" in result.data["script"]


def test_prepare_submit_script_keeps_existing_response_shape():
    prepared = prepare_submit_script("帮我提交一个作业运行 python train.py，4 核，10 分钟")

    assert prepared["ready"]
    assert prepared["script"].startswith("#!/bin/bash")
    assert "python train.py" in prepared["script"]
    assert "请确认后再提交" in prepared["message"]
    assert prepared["tool_call"]["tool"] == "prepare_slurm_job"


def test_prepare_slurm_job_tool_call_missing_command_matches_existing_message():
    prepared = prepare_submit_script("帮我提交一个作业，4 核，10 分钟")

    assert not prepared["ready"]
    assert prepared["script"] is None
    assert "请告诉我要运行的命令" in prepared["message"]
    assert prepared["tool_call"]["tool"] == "prepare_slurm_job"


if __name__ == "__main__":
    test_prepare_slurm_job_tool_call_extracts_arguments()
    test_execute_prepare_slurm_job_tool_call_returns_preview_result()
    test_prepare_submit_script_keeps_existing_response_shape()
    test_prepare_slurm_job_tool_call_missing_command_matches_existing_message()
    print("All Slurm tool calling checks passed.")
