from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
import os
from typing import Any, AsyncIterator

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from modules.mcp_client.audit import now_ms, record_external_tool_call
from modules.mcp_client.config import ExternalMcpServerConfig, enabled_external_mcp_config
from modules.mcp_client.formatters import external_tool_payload, mcp_content_to_text, public_tool_name
from modules.mcp_client.tool_registry import ExternalMcpTool, ExternalMcpToolRegistry


class ExternalMcpClientManager:
    def __init__(self, configs: list[ExternalMcpServerConfig] | None = None):
        self.configs = configs if configs is not None else enabled_external_mcp_config()
        self.registry = ExternalMcpToolRegistry()

    async def start(self) -> None:
        await self.refresh_tools()

    async def stop(self) -> None:
        return None

    async def refresh_tools(self) -> list[ExternalMcpTool]:
        self.registry = ExternalMcpToolRegistry()
        for config in self.configs:
            if not config.enabled:
                continue
            raw_tools = await self._list_server_tools(config)
            self.registry.register_many(config, raw_tools)
        return self.registry.all()

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = self._get_config(server_name)
        public_name = public_tool_name(server_name, tool_name)
        arguments = dict(arguments or {})
        started = now_ms()

        if tool_name not in set(config.allowed_tools):
            result = external_tool_payload(
                ok=False,
                server=server_name,
                tool=tool_name,
                public_tool=public_name,
                content=f"外部 MCP 工具未在 allowed_tools 白名单中: {server_name}.{tool_name}",
                error={"type": "ToolNotAllowed", "message": "tool is not allowed"},
                risk=config.risk_level,
            )
            record_external_tool_call(
                server=server_name,
                tool=tool_name,
                public_tool=public_name,
                arguments=arguments,
                ok=False,
                duration_ms=now_ms() - started,
                error=result["message"],
            )
            return result

        try:
            async with self._session(config) as session:
                with anyio.fail_after(config.timeout_seconds):
                    response = await session.call_tool(tool_name, arguments)
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            result = external_tool_payload(
                ok=False,
                server=server_name,
                tool=tool_name,
                public_tool=public_name,
                content=f"外部 MCP 工具调用失败: {message}",
                error={"type": type(error).__name__, "message": str(error)},
                risk=config.risk_level,
            )
            record_external_tool_call(
                server=server_name,
                tool=tool_name,
                public_tool=public_name,
                arguments=arguments,
                ok=False,
                duration_ms=now_ms() - started,
                error=message,
            )
            return result

        content = mcp_content_to_text(getattr(response, "content", None))
        is_error = bool(getattr(response, "isError", False) or getattr(response, "is_error", False))
        data = _model_dump(response)
        result = external_tool_payload(
            ok=not is_error,
            server=server_name,
            tool=tool_name,
            public_tool=public_name,
            content=content,
            data={"raw_result": data},
            error={"type": "ExternalToolError", "message": content} if is_error else None,
            risk=config.risk_level,
        )
        record_external_tool_call(
            server=server_name,
            tool=tool_name,
            public_tool=public_name,
            arguments=arguments,
            ok=not is_error,
            duration_ms=now_ms() - started,
            error=content if is_error else None,
        )
        return result

    async def call_public_tool(self, public_tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.registry.has(public_tool):
            await self.refresh_tools()

        tool = self.registry.get(public_tool)
        if tool is None:
            return external_tool_payload(
                ok=False,
                server="",
                tool=public_tool,
                public_tool=public_tool,
                content=f"未找到外部 MCP 工具: {public_tool}",
                error={"type": "ToolNotFound", "message": "external tool is not registered"},
            )
        return await self.call_tool(tool.server_name, tool.tool_name, arguments)

    async def doctor(self) -> dict[str, Any]:
        servers = []
        ok = True
        for config in self.configs:
            item: dict[str, Any] = {
                "name": config.name,
                "enabled": config.enabled,
                "transport": config.transport,
                "allowed_tools": list(config.allowed_tools),
            }
            if not config.enabled:
                item["ok"] = True
                item["message"] = "未启用，已跳过。"
                servers.append(item)
                continue
            try:
                raw_tools = await self._list_server_tools(config)
            except Exception as error:
                ok = False
                item["ok"] = False
                item["message"] = f"{type(error).__name__}: {error}"
            else:
                allowed = set(config.allowed_tools)
                discovered = [_tool_name(tool) for tool in raw_tools]
                injected = [name for name in discovered if name in allowed]
                item["ok"] = True
                item["message"] = "连接成功。"
                item["discovered_tools"] = discovered
                item["injected_tools"] = injected
            servers.append(item)
        return {"ok": ok, "servers": servers}

    async def _list_server_tools(self, config: ExternalMcpServerConfig) -> list[Any]:
        async with self._session(config) as session:
            with anyio.fail_after(config.timeout_seconds):
                response = await session.list_tools()
        return list(getattr(response, "tools", []) or [])

    def _get_config(self, server_name: str) -> ExternalMcpServerConfig:
        for config in self.configs:
            if config.name == server_name:
                return config
        raise ValueError(f"未找到外部 MCP server: {server_name}")

    @asynccontextmanager
    async def _session(self, config: ExternalMcpServerConfig) -> AsyncIterator[ClientSession]:
        timeout = timedelta(seconds=max(1, config.timeout_seconds))
        async with _transport(config) as streams:
            read_stream, write_stream = streams[:2]
            async with ClientSession(read_stream, write_stream, read_timeout_seconds=timeout) as session:
                with anyio.fail_after(config.timeout_seconds):
                    await session.initialize()
                yield session


@asynccontextmanager
async def _transport(config: ExternalMcpServerConfig):
    if config.transport == "stdio":
        params = StdioServerParameters(
            command=config.command or "",
            args=list(config.args),
            env=dict(config.env) or None,
            cwd=config.cwd,
        )
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as streams:
                yield streams
        return

    async with streamablehttp_client(config.url or "", timeout=config.timeout_seconds) as streams:
        yield streams


def load_manager(config_path: str | None = None) -> ExternalMcpClientManager:
    return ExternalMcpClientManager(enabled_external_mcp_config(config_path))


def list_external_tools(config_path: str | None = None) -> list[ExternalMcpTool]:
    async def _run() -> list[ExternalMcpTool]:
        manager = load_manager(config_path)
        return await manager.refresh_tools()

    return anyio.run(_run)


def call_external_tool(
    public_tool: str,
    arguments: dict[str, Any] | None = None,
    *,
    config_path: str | None = None,
) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        manager = load_manager(config_path)
        await manager.refresh_tools()
        return await manager.call_public_tool(public_tool, arguments)

    return anyio.run(_run)


def doctor_external_mcp(config_path: str | None = None) -> dict[str, Any]:
    async def _run() -> dict[str, Any]:
        manager = load_manager(config_path)
        return await manager.doctor()

    return anyio.run(_run)


def _tool_name(raw_tool: Any) -> str:
    if isinstance(raw_tool, dict):
        return str(raw_tool.get("name") or "")
    return str(getattr(raw_tool, "name", "") or "")


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_model_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_dump(item) for key, item in value.items()}
    return value
