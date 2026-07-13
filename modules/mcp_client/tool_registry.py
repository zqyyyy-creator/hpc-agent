from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.mcp_client.config import ExternalMcpServerConfig
from modules.mcp_client.formatters import public_tool_name


@dataclass(frozen=True)
class ExternalMcpTool:
    server_name: str
    tool_name: str
    public_name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "read_only"

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "public_name": self.public_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "risk_level": self.risk_level,
        }


class ExternalMcpToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ExternalMcpTool] = {}

    def register_many(
        self,
        config: ExternalMcpServerConfig,
        raw_tools: list[Any],
    ) -> list[ExternalMcpTool]:
        registered: list[ExternalMcpTool] = []
        allowed = set(config.allowed_tools)
        if not allowed:
            return registered

        for raw_tool in raw_tools:
            tool_name = _tool_attr(raw_tool, "name")
            if not tool_name or tool_name not in allowed:
                continue

            public_name = public_tool_name(config.name, tool_name)
            tool = ExternalMcpTool(
                server_name=config.name,
                tool_name=tool_name,
                public_name=public_name,
                description=_tool_attr(raw_tool, "description") or config.description or "外部 MCP 工具。",
                input_schema=_tool_schema(raw_tool),
                risk_level=config.risk_level or "read_only",
            )
            self._tools[public_name] = tool
            registered.append(tool)

        return registered

    def all(self) -> list[ExternalMcpTool]:
        return sorted(self._tools.values(), key=lambda item: item.public_name)

    def get(self, public_name: str) -> ExternalMcpTool | None:
        return self._tools.get(public_name)

    def has(self, public_name: str) -> bool:
        return public_name in self._tools


def _tool_attr(raw_tool: Any, name: str) -> str:
    if isinstance(raw_tool, dict):
        return str(raw_tool.get(name) or "")
    return str(getattr(raw_tool, name, "") or "")


def _tool_schema(raw_tool: Any) -> dict[str, Any]:
    if isinstance(raw_tool, dict):
        schema = raw_tool.get("inputSchema") or raw_tool.get("input_schema") or {}
        return dict(schema) if isinstance(schema, dict) else {}

    schema = getattr(raw_tool, "inputSchema", None) or getattr(raw_tool, "input_schema", None) or {}
    if hasattr(schema, "model_dump"):
        schema = schema.model_dump()
    return dict(schema) if isinstance(schema, dict) else {}


def format_tool_list(tools: list[ExternalMcpTool]) -> str:
    if not tools:
        return "当前没有注入任何外部 MCP 工具。"

    lines = ["已注入外部 MCP 工具:"]
    for tool in tools:
        lines.append(
            f"- {tool.public_name} -> {tool.server_name}.{tool.tool_name} "
            f"[risk={tool.risk_level}] {tool.description}"
        )
    return "\n".join(lines)

