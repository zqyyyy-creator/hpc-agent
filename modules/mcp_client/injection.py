from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from modules.core.tool_calling import ToolResult
from modules.mcp_client.client_manager import call_external_tool, list_external_tools
from modules.mcp_client.tool_registry import ExternalMcpTool


@dataclass
class ExternalMcpMatch:
    tool: ExternalMcpTool
    arguments: dict[str, Any]
    score: int
    reason: str


def maybe_execute_external_mcp_tool(question: str) -> ToolResult | None:
    match = match_external_mcp_tool(question)
    if match is None:
        return None

    result = call_external_tool(match.tool.public_name, match.arguments)
    message = str(result.get("message") or "")
    if result.get("content") and result.get("content") != message:
        message = str(result["content"])

    data = {
        "external_mcp": True,
        "match": {
            "public_tool": match.tool.public_name,
            "server": match.tool.server_name,
            "tool": match.tool.tool_name,
            "score": match.score,
            "reason": match.reason,
            "arguments": match.arguments,
        },
        "raw_payload": result,
    }
    return ToolResult(
        success=bool(result.get("ok")),
        message=message,
        data=data,
    )


def match_external_mcp_tool(question: str) -> ExternalMcpMatch | None:
    text = str(question or "").strip()
    if not text:
        return None

    try:
        tools = list_external_tools()
    except Exception:
        return None
    if not tools:
        return None

    explicit = _match_explicit_tool(text, tools)
    if explicit is not None:
        return explicit

    candidates = []
    for tool in tools:
        score = _score_tool(text, tool)
        if score <= 0:
            continue
        arguments = _infer_arguments(text, tool)
        if arguments is None:
            continue
        candidates.append(ExternalMcpMatch(tool=tool, arguments=arguments, score=score, reason="自然语言匹配外部 MCP 工具"))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[0]


def _match_explicit_tool(text: str, tools: list[ExternalMcpTool]) -> ExternalMcpMatch | None:
    for tool in tools:
        if tool.public_name not in text:
            continue
        arguments = _extract_json_object(text) or _infer_arguments(text, tool) or {}
        return ExternalMcpMatch(tool=tool, arguments=arguments, score=100, reason="用户显式指定外部 MCP 工具名")
    return None


def _score_tool(text: str, tool: ExternalMcpTool) -> int:
    normalized = text.lower()
    compact = "".join(normalized.split())
    score = 0

    if tool.tool_name.lower() in normalized or tool.public_name.lower() in normalized:
        score += 40

    if "read" in tool.tool_name.lower() or "读取" in tool.description:
        if any(marker in compact for marker in ("读取", "读一下", "查看文件", "打开文件", "readfile", "read_file")):
            score += 35

    if "list" in tool.tool_name.lower() or "目录" in tool.description:
        if any(marker in compact for marker in ("列出目录", "查看目录", "目录里", "listdirectory", "list_directory")):
            score += 35

    for token in _tokens(tool.description):
        if len(token) >= 3 and token in normalized:
            score += 3

    return score


def _infer_arguments(text: str, tool: ExternalMcpTool) -> dict[str, Any] | None:
    explicit = _extract_json_object(text)
    if explicit is not None:
        return explicit

    schema = tool.input_schema or {}
    properties = schema.get("properties") if isinstance(schema, dict) else {}
    if not isinstance(properties, dict):
        properties = {}

    path = _extract_path(text)
    if path:
        for key in ("path", "file", "filepath", "file_path", "directory", "dir"):
            if key in properties or key in {"path", "directory"}:
                if "list" in tool.tool_name.lower() and key in {"directory", "dir"}:
                    return {key: path}
                if "list" not in tool.tool_name.lower() and key in {"path", "file", "filepath", "file_path"}:
                    return {key: path}
        if "list" in tool.tool_name.lower():
            return {"path": path}
        return {"path": path}

    required = schema.get("required") if isinstance(schema, dict) else []
    if not required:
        return {}
    return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_path(text: str) -> str | None:
    quoted = re.search(r"[`'\"]([^`'\"]+)[`'\"]", text)
    if quoted:
        return quoted.group(1).strip()

    path_like = re.search(
        r"((?:[A-Za-z]:)?/?(?:[\w.\-]+/)+[\w.\-]+|[\w.\-]+\.(?:md|txt|json|yaml|yml|py|sh|log|out|err))",
        text,
    )
    if path_like:
        return path_like.group(1).strip()

    tail = re.search(r"(?:读取|查看|打开|列出|目录)\s*([^\s，。；,;]+)", text)
    if tail:
        return tail.group(1).strip()
    return None


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\w一-龥]{2,}", str(text).lower())

