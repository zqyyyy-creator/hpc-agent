from tests import _bootstrap  # noqa: F401

from modules.core.conversation_state import ConversationState
from modules.slurm.job_query import (
    execute_vasp_postprocess_tool_call,
    handle_vasp_postprocess_request,
    make_vasp_postprocess_tool_call,
    validate_vasp_postprocess_tool_call,
)


def test_make_register_vasp_tool_call():
    call = make_vasp_postprocess_tool_call(
        "登记 VASP 作业 11817144，目录名 si_static_test",
        "register_vasp_job",
    )

    assert call.tool == "register_vasp_job"
    assert call.arguments["job_id"] == "11817144"
    assert call.arguments["selector"] == "si_static_test"


def test_register_vasp_tool_call_records_state():
    state = ConversationState()

    result = handle_vasp_postprocess_request(
        "登记 VASP 作业 11817144，目录名 si_static_test",
        "register_vasp_job",
        state=state,
        executors={
            "register_vasp_job": lambda call: {
                "success": True,
                "message": f"registered {call.arguments['job_id']}",
            },
        },
    )

    assert result.success
    assert result.message == "registered 11817144"
    assert state.last_vasp_job_id == "11817144"
    assert state.last_job_id == "11817144"


def test_sync_vasp_output_uses_explicit_job_id():
    result = handle_vasp_postprocess_request(
        "同步 VASP 作业 11817144 的输出",
        "sync_vasp_output",
        state=ConversationState(),
        executors={
            "sync_vasp_output": lambda call: f"synced {call.arguments['job_id']}",
        },
    )

    assert result.success
    assert result.message == "synced 11817144"
    assert result.data["job_id"] == "11817144"


def test_sync_vasp_output_uses_last_vasp_job_id():
    state = ConversationState()
    state.record_job("11817144", metadata={"kind": "vasp", "type": "vasp"})
    call = make_vasp_postprocess_tool_call("同步刚才那个 VASP 作业的输出", "sync_vasp_output")
    validated = validate_vasp_postprocess_tool_call(call, state=state)

    assert validated.tool == "sync_vasp_output"
    assert validated.arguments["job_id"] == "11817144"


def test_sync_vasp_output_without_context_asks_for_job_id():
    result = handle_vasp_postprocess_request(
        "同步刚才那个 VASP 作业的输出",
        "sync_vasp_output",
        state=ConversationState(),
    )

    assert not result.success
    assert "VASP Job ID" in result.message


def test_register_vasp_requires_selector():
    result = execute_vasp_postprocess_tool_call(
        {"tool": "register_vasp_job", "arguments": {"job_id": "11817144"}},
        state=ConversationState(),
    )

    assert not result.success
    assert "远端 VASP 输出目录" in result.message


if __name__ == "__main__":
    test_make_register_vasp_tool_call()
    test_register_vasp_tool_call_records_state()
    test_sync_vasp_output_uses_explicit_job_id()
    test_sync_vasp_output_uses_last_vasp_job_id()
    test_sync_vasp_output_without_context_asks_for_job_id()
    test_register_vasp_requires_selector()
    print("All VASP postprocess tool calling checks passed.")
