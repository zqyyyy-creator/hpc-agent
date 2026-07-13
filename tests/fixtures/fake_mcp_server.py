from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


TOOLS = [
    {
        "name": "echo",
        "description": "回显文本。",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    {
        "name": "read_file",
        "description": "读取测试允许目录下的文件内容。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "列出目录内容。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "delete_file",
        "description": "危险工具，测试中不应被白名单注入。",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        if "id" not in request:
            continue
        response = handle_request(request)
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-external-mcp", "version": "0.1.0"},
            },
        }

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            text = call_tool(str(name), arguments)
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as error:
            result = {
                "content": [{"type": "text", "text": f"{type(error).__name__}: {error}"}],
                "isError": True,
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def call_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "echo":
        return f"echo: {arguments.get('text', '')}"
    if name == "read_file":
        return _resolve_path(str(arguments.get("path") or "")).read_text(encoding="utf-8")
    if name == "list_directory":
        return "\n".join(sorted(child.name for child in _resolve_path(str(arguments.get("path") or "")).iterdir()))
    if name == "delete_file":
        return f"not deleted: {arguments.get('path', '')}"
    raise ValueError(f"unknown tool: {name}")


def _resolve_path(path: str) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    return target


if __name__ == "__main__":
    main()
