from __future__ import annotations

import os
from typing import Any

from modules.core.tool_calling import ToolResult


DEFAULT_MAX_TEXT_CHARS = 12000
SCHEMA_VERSION = "2026-07-13"


def max_text_chars() -> int:
    raw_value = os.getenv("HPC_AGENT_MCP_MAX_LOG_CHARS", "").strip()
    if not raw_value:
        return DEFAULT_MAX_TEXT_CHARS

    try:
        return max(1000, int(raw_value))
    except ValueError:
        return DEFAULT_MAX_TEXT_CHARS


def truncate_text(text: str, limit: int | None = None) -> str:
    active_limit = limit or max_text_chars()
    if len(text) <= active_limit:
        return text
    return text[:active_limit].rstrip() + "\n...（MCP 输出已截断）"


def scrub_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***"
            if _looks_secret_key(str(key))
            else scrub_secrets(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]

    if isinstance(value, tuple):
        return tuple(scrub_secrets(item) for item in value)

    return value


def tool_result_payload(result: ToolResult, *, risk: str = "read_only") -> dict[str, Any]:
    data = scrub_secrets(result.data)
    payload = {
        "ok": result.success,
        "risk": risk,
        "message": truncate_text(result.message or ""),
        "data": data,
        "tool_call": scrub_secrets(result.tool_call.to_dict()) if result.tool_call else None,
    }
    return normalize_payload(payload)


def text_payload(message: str, *, ok: bool = True, risk: str = "read_only", **data: Any) -> dict[str, Any]:
    payload = {
        "ok": ok,
        "risk": risk,
        "message": truncate_text(message),
        **scrub_secrets(data),
    }
    return normalize_payload(payload)


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """返回稳定 MCP envelope，同时保留兼容旧调用的顶层字段。"""
    normalized = dict(payload)
    message = truncate_text(str(normalized.get("message") or ""))
    reply = str(normalized.get("reply") or message)
    plain_text = str(normalized.get("plain_text") or reply or message)
    data = normalized.get("data")
    if not isinstance(data, dict):
        data = {}

    reserved = {
        "ok",
        "risk",
        "message",
        "reply",
        "plain_text",
        "data",
        "next_step",
        "requires_confirmation",
        "required_env",
        "schema_version",
    }
    structured = {
        key: value
        for key, value in normalized.items()
        if key not in reserved
    }
    if structured:
        data = {**structured, **data}

    normalized["ok"] = bool(normalized.get("ok"))
    normalized["risk"] = str(normalized.get("risk") or "read_only")
    normalized["message"] = message
    normalized["reply"] = truncate_text(reply, limit=2000)
    normalized["plain_text"] = truncate_text(plain_text, limit=4000)
    normalized["data"] = scrub_secrets(data)
    normalized["requires_confirmation"] = bool(normalized.get("requires_confirmation", False))
    normalized["schema_version"] = SCHEMA_VERSION

    return normalized


def _looks_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("token", "secret", "api_key", "apikey", "password", "private_key"))
