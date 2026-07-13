from __future__ import annotations

import argparse
import json
from typing import Any

from modules.mcp_client.client_manager import call_external_tool, doctor_external_mcp, list_external_tools
from modules.mcp_client.config import default_external_mcp_config_path
from modules.mcp_client.tool_registry import format_tool_list


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HPC Agent 外部 MCP tools 注入管理命令。")
    parser.add_argument(
        "--config",
        default=None,
        help=f"外部 MCP 配置文件路径，默认 {default_external_mcp_config_path()}",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="检查外部 MCP server 是否可连接、工具是否可发现。")
    subparsers.add_parser("list-tools", help="列出通过 allowed_tools 注入的外部 MCP tools。")

    call_parser = subparsers.add_parser("call", help="调用一个已注入的外部 MCP tool。")
    call_parser.add_argument("tool", help="工具名，例如 external_filesystem_read_file")
    call_parser.add_argument("arguments", nargs="?", default="{}", help="JSON 参数，例如 '{\"path\":\"README.md\"}'")

    args = parser.parse_args(argv)

    if args.command == "doctor":
        result = doctor_external_mcp(args.config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if args.command == "list-tools":
        tools = list_external_tools(args.config)
        print(format_tool_list(tools))
        return 0

    if args.command == "call":
        arguments = _parse_json_object(args.arguments)
        result = call_external_tool(args.tool, arguments, config_path=args.config)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    parser.print_help()
    return 1


def _parse_json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise SystemExit(f"arguments 必须是 JSON 对象: {error}") from error
    if not isinstance(parsed, dict):
        raise SystemExit("arguments 必须是 JSON 对象。")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())

