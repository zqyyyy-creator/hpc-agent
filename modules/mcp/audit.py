from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.core.paths import USER_DATA_DIR
from modules.mcp.formatters import scrub_secrets, truncate_text


AUDIT_ENV = "HPC_AGENT_MCP_AUDIT_LOG"
DEFAULT_AUDIT_PATH = USER_DATA_DIR / "mcp_audit.jsonl"


def audit_path() -> Path:
    raw_value = os.getenv(AUDIT_ENV, "").strip()
    return Path(raw_value).expanduser() if raw_value else DEFAULT_AUDIT_PATH


def record_tool_call(
    tool_name: str,
    *,
    risk: str,
    arguments: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "risk": risk,
        "arguments": scrub_secrets(arguments or {}),
        "ok": bool((result or {}).get("ok")),
        "message": truncate_text(str((result or {}).get("message", "")), limit=1000),
        "required_env": (result or {}).get("required_env"),
        "requires_confirmation": (result or {}).get("requires_confirmation"),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def audited(
    tool_name: str,
    *,
    risk: str,
    arguments: dict[str, Any] | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    record_tool_call(tool_name, risk=risk, arguments=arguments, result=result)
    return result

