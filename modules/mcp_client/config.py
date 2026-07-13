from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from modules.core.paths import PROJECT_ROOT, USER_CONFIG_DIR


Transport = Literal["stdio", "streamable_http"]


@dataclass
class ExternalMcpServerConfig:
    name: str
    enabled: bool
    transport: Transport
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 20
    allowed_tools: list[str] = field(default_factory=list)
    risk_level: str = "read_only"
    description: str = ""


def default_external_mcp_config_path() -> Path:
    explicit = os.getenv("HPC_AGENT_EXTERNAL_MCP_CONFIG", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    user_config = USER_CONFIG_DIR / "external_mcp_servers.yaml"
    if user_config.is_file():
        return user_config

    return PROJECT_ROOT / "config" / "external_mcp_servers.yaml"


def load_external_mcp_config(path: str | Path | None = None) -> list[ExternalMcpServerConfig]:
    config_path = Path(path).expanduser() if path else default_external_mcp_config_path()
    if not config_path.is_file():
        return []

    data = _load_yaml_like(config_path)
    servers = data.get("servers") if isinstance(data, dict) else {}
    if not isinstance(servers, dict):
        raise ValueError("external_mcp_servers.yaml 中 servers 必须是对象。")

    configs: list[ExternalMcpServerConfig] = []
    for name, raw_config in servers.items():
        if raw_config is None:
            raw_config = {}
        if not isinstance(raw_config, dict):
            raise ValueError(f"server {name} 配置必须是对象。")
        configs.append(_server_config_from_mapping(str(name), raw_config))
    return configs


def enabled_external_mcp_config(path: str | Path | None = None) -> list[ExternalMcpServerConfig]:
    return [config for config in load_external_mcp_config(path) if config.enabled]


def _server_config_from_mapping(name: str, data: dict[str, Any]) -> ExternalMcpServerConfig:
    enabled = _as_bool(data.get("enabled", False))
    transport = str(data.get("transport") or "stdio").strip().lower().replace("-", "_")
    if transport not in {"stdio", "streamable_http"}:
        raise ValueError(f"server {name} transport 不支持: {transport}")

    args = _as_string_list(data.get("args", []))
    allowed_tools = _as_string_list(data.get("allowed_tools", []))
    env = data.get("env") or {}
    if not isinstance(env, dict):
        raise ValueError(f"server {name} env 必须是对象。")

    config = ExternalMcpServerConfig(
        name=name,
        enabled=enabled,
        transport=transport,  # type: ignore[arg-type]
        command=_optional_str(data.get("command")),
        args=args,
        url=_optional_str(data.get("url")),
        cwd=_optional_str(data.get("cwd")),
        env={str(key): str(value) for key, value in env.items()},
        timeout_seconds=max(1, int(data.get("timeout_seconds") or 20)),
        allowed_tools=allowed_tools,
        risk_level=str(data.get("risk_level") or "read_only"),
        description=str(data.get("description") or ""),
    )
    _validate_server_config(config)
    return config


def _validate_server_config(config: ExternalMcpServerConfig) -> None:
    if not config.enabled:
        return
    if config.transport == "stdio" and not config.command:
        raise ValueError(f"server {config.name} 使用 stdio 时必须配置 command。")
    if config.transport == "streamable_http" and not config.url:
        raise ValueError(f"server {config.name} 使用 streamable_http 时必须配置 url。")


def _load_yaml_like(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
    except Exception:
        yaml = None
    if yaml is not None:
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} 顶层必须是对象。")
        return loaded

    return _parse_small_yaml(text)


def _parse_small_yaml(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, result)]
    last_key_at_indent: dict[int, tuple[dict[str, Any], str]] = {}

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            value = _parse_scalar(line[2:].strip())
            if not isinstance(parent, list):
                container, key = last_key_at_indent.get(indent - 2, ({}, ""))
                if key:
                    container[key] = []
                    parent = container[key]
                    stack.append((indent - 1, parent))
            if not isinstance(parent, list):
                raise ValueError(f"无法解析列表行: {raw_line}")
            parent.append(value)
            continue

        key, separator, value_text = line.partition(":")
        if not separator:
            raise ValueError(f"无法解析配置行: {raw_line}")

        key = key.strip()
        if value_text.strip() == "":
            value: Any = {}
        else:
            value = _parse_scalar(value_text.strip())

        if not isinstance(parent, dict):
            raise ValueError(f"父节点不是对象，无法设置 {key}")
        parent[key] = value
        last_key_at_indent[indent] = (parent, key)

        if value == {}:
            stack.append((indent, value))

    _convert_empty_dict_lists(result)
    return result


def _convert_empty_dict_lists(value: Any) -> None:
    if not isinstance(value, dict):
        return
    for key, item in list(value.items()):
        if isinstance(item, dict):
            _convert_empty_dict_lists(item)
        elif isinstance(item, list):
            for child in item:
                _convert_empty_dict_lists(child)


def _parse_scalar(value: str) -> Any:
    if value in {"{}", "[]"}:
        return {} if value == "{}" else []
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        try:
            return ast.literal_eval(value)
        except Exception:
            return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [str(value)]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

