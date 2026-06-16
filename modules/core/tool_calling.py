from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    confidence: float | None = None
    needs_confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: dict | "ToolCall") -> "ToolCall":
        if isinstance(value, ToolCall):
            return value

        return cls(
            tool=value.get("tool") or value.get("name") or "",
            arguments=dict(value.get("arguments") or {}),
            source=value.get("source", "unknown"),
            confidence=value.get("confidence"),
            needs_confirmation=bool(value.get("needs_confirmation", False)),
            metadata=dict(value.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "tool": self.tool,
            "arguments": self.arguments,
            "source": self.source,
            "needs_confirmation": self.needs_confirmation,
        }

        if self.confidence is not None:
            data["confidence"] = self.confidence

        if self.metadata:
            data["metadata"] = self.metadata

        return data


@dataclass
class ToolResult:
    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    tool_call: ToolCall | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "tool_call": self.tool_call.to_dict() if self.tool_call else None,
        }


class ToolRegistry:
    def __init__(self):
        self._handlers: dict[str, Callable[[ToolCall], ToolResult]] = {}

    def register(self, tool_name: str, handler: Callable[[ToolCall], ToolResult]):
        if not tool_name:
            raise ValueError("tool_name 不能为空。")

        self._handlers[tool_name] = handler

    def has(self, tool_name: str) -> bool:
        return tool_name in self._handlers

    def execute(self, tool_call: ToolCall | dict) -> ToolResult:
        call = ToolCall.from_mapping(tool_call)
        handler = self._handlers.get(call.tool)

        if not handler:
            return ToolResult(
                success=False,
                message=f"不支持的工具: {call.tool}",
                tool_call=call,
            )

        return handler(call)


def ensure_allowed_tool(tool_call: ToolCall | dict, allowed_tools: set[str]) -> ToolCall:
    call = ToolCall.from_mapping(tool_call)

    if call.tool not in allowed_tools:
        raise ValueError(f"不支持的工具: {call.tool}")

    return call
