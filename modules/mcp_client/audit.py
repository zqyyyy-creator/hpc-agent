from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.core.paths import USER_DATA_DIR
from modules.mcp.formatters import scrub_secrets, truncate_text


AUDIT_ENV = "HPC_AGENT_EXTERNAL_MCP_AUDIT_LOG"
DEFAULT_AUDIT_PATH = USER_DATA_DIR / "external_mcp_audit.jsonl"


def audit_path() -> Path:
    raw_value = os.getenv(AUDIT_ENV, "").strip()
    return Path(raw_value).expanduser() if raw_value else DEFAULT_AUDIT_PATH


def now_ms() -> float:
    return time.perf_counter() * 1000


def record_external_tool_call(
    *,
    server: str,
    tool: str,
    public_tool: str,
    arguments: dict[str, Any] | None,
    ok: bool,
    duration_ms: float,
    error: str | None = None,
) -> None:
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "external_mcp",
        "server": server,
        "tool": tool,
        "public_tool": public_tool,
        "arguments_preview": scrub_secrets(arguments or {}),
        "ok": bool(ok),
        "duration_ms": round(duration_ms, 2),
        "error": truncate_text(error or "", limit=1000) if error else None,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

