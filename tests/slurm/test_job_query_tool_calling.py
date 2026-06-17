from tests import _bootstrap  # noqa: F401

from modules.core.conversation_state import ConversationState
from modules.slurm.job_query import (
    diagnose_job_request,
    execute_job_query_tool_call,
    handle_job_query_request,
    make_job_query_tool_call,
    validate_job_query_tool_call,
)
import modules.slurm.job_query as job_query
from modules.routing.router import detect_intent


def test_make_job_query_tool_call_with_explicit_job_id():
    call = make_job_query_tool_call("查看 12345 的状态", "job_status")

    assert call.tool == "query_job_status"
    assert call.arguments["job_id"] == "12345"


def test_job_query_uses_last_job_id_from_state():
    state = ConversationState()
    state.record_job("12345", "/remote/job")
    call = make_job_query_tool_call("查看刚才那个作业", "job_status")
    validated = validate_job_query_tool_call(call, state=state)

    assert validated.tool == "query_job_status"
    assert validated.arguments["job_id"] == "12345"


def test_job_query_without_context_asks_for_job_id():
    state = ConversationState()
    result = handle_job_query_request("查看刚才那个作业", "job_status", state=state)

    assert not result.success
    assert "请提供 job_id" in result.message


def test_execute_job_query_tool_call_uses_injected_query_function():
    state = ConversationState()
    state.record_job("12345")
    result = execute_job_query_tool_call(
        {"tool": "read_job_output", "arguments": {"job_id": "last"}},
        state=state,
        query_funcs={
            "read_job_output": lambda job_id: f"output for {job_id}",
        },
    )

    assert result.success
    assert result.message == "output for 12345"
    assert result.data["job_id"] == "12345"


def test_router_detects_last_job_references():
    cases = {
        "查看刚才那个作业": "job_status",
        "看它的输出": "job_output",
        "看上一个任务的错误日志": "job_error",
    }

    for request, expected in cases.items():
        assert detect_intent(request) == expected


def test_diagnose_job_request_returns_next_steps():
    original_status = job_query.query_job_status
    original_output = job_query.query_job_output
    original_error = job_query.query_job_error

    try:
        job_query.query_job_status = lambda job_id: f"status {job_id}"
        job_query.query_job_output = lambda job_id: f"output {job_id}"
        job_query.query_job_error = lambda job_id: f"error {job_id}"
        answer = diagnose_job_request("诊断作业 12345", state=ConversationState())
    finally:
        job_query.query_job_status = original_status
        job_query.query_job_output = original_output
        job_query.query_job_error = original_error

    assert "作业诊断摘要" in answer
    assert "Job ID: 12345" in answer
    assert "错误日志摘要" in answer
    assert "建议下一步命令" in answer
    assert "读取 12345 的错误日志" in answer


if __name__ == "__main__":
    test_make_job_query_tool_call_with_explicit_job_id()
    test_job_query_uses_last_job_id_from_state()
    test_job_query_without_context_asks_for_job_id()
    test_execute_job_query_tool_call_uses_injected_query_function()
    test_router_detects_last_job_references()
    test_diagnose_job_request_returns_next_steps()
    print("All job query tool calling checks passed.")
