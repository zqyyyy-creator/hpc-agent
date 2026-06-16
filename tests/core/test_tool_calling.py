from tests import _bootstrap  # noqa: F401

from modules.core.tool_calling import ToolCall, ToolRegistry, ToolResult, ensure_allowed_tool


def test_tool_call_roundtrip():
    call = ToolCall(
        tool="generate_test_file",
        arguments={"kind": "hostname"},
        source="rules",
        confidence=0.9,
        needs_confirmation=False,
    )
    data = call.to_dict()
    restored = ToolCall.from_mapping(data)

    assert restored.tool == "generate_test_file"
    assert restored.arguments["kind"] == "hostname"
    assert restored.source == "rules"
    assert restored.confidence == 0.9


def test_ensure_allowed_tool_rejects_unknown_tool():
    try:
        ensure_allowed_tool({"tool": "bad_tool", "arguments": {}}, {"known_tool"})
    except ValueError as error:
        assert "不支持的工具" in str(error)
    else:
        raise AssertionError("Expected unknown tool to be rejected")


def test_tool_registry_executes_registered_handler():
    registry = ToolRegistry()

    def handler(call: ToolCall):
        return ToolResult(
            success=True,
            message=f"ran {call.tool}",
            data={"value": call.arguments["value"]},
            tool_call=call,
        )

    registry.register("echo_tool", handler)
    result = registry.execute({"tool": "echo_tool", "arguments": {"value": 42}})

    assert result.success
    assert result.message == "ran echo_tool"
    assert result.data["value"] == 42
    assert result.tool_call.tool == "echo_tool"


if __name__ == "__main__":
    test_tool_call_roundtrip()
    test_ensure_allowed_tool_rejects_unknown_tool()
    test_tool_registry_executes_registered_handler()
    print("All tool calling checks passed.")
