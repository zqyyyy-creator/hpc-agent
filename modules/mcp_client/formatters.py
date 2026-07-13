from __future__ import annotations

from typing import Any

from modules.mcp.formatters import normalize_payload, scrub_secrets, truncate_text


def public_tool_name(server_name: str, tool_name: str) -> str:
    return f"external_{_safe_name(server_name)}_{_safe_name(tool_name)}"


def external_tool_payload(
    *,
    ok: bool,
    server: str,
    tool: str,
    public_tool: str,
    content: str = "",
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    risk: str = "read_only",
) -> dict[str, Any]:
    message = content or ("外部 MCP 工具调用成功。" if ok else "外部 MCP 工具调用失败。")
    payload = {
        "ok": ok,
        "kind": "external_mcp_tool_result",
        "source": "external_mcp",
        "risk": risk,
        "message": truncate_text(message),
        "server": server,
        "tool": tool,
        "public_tool": public_tool,
        "content": truncate_text(content),
        "data": scrub_secrets(data or {}),
        "error": scrub_secrets(error) if error else None,
    }
    return normalize_payload(payload)


def mcp_content_to_text(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(str(text))
                continue
            if isinstance(item, dict) and item.get("text") is not None:
                parts.append(str(item["text"]))
                continue
            parts.append(str(item))
        return "\n".join(part for part in parts if part)

    text = getattr(content, "text", None)
    if text is not None:
        return str(text)

    return str(content)


def _safe_name(value: str) -> str:
    chars = []
    for char in str(value).strip():
        if char.isalnum():
            chars.append(char.lower())
        else:
            chars.append("_")
    name = "".join(chars).strip("_")
    while "__" in name:
        name = name.replace("__", "_")
    return name or "tool"

