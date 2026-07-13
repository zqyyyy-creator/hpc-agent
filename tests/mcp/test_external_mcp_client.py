from __future__ import annotations

import json
import sys
from pathlib import Path

from modules.core.agent_runtime import execute_answer_intent
from modules.mcp_client.client_manager import call_external_tool, doctor_external_mcp, list_external_tools
from modules.mcp_client.config import load_external_mcp_config


def _write_config(tmp_path: Path, target_file: Path) -> Path:
    config_path = tmp_path / "external_mcp_servers.yaml"
    fake_server = Path(__file__).resolve().parents[1] / "fixtures" / "fake_mcp_server.py"
    config_path.write_text(
        "\n".join([
            "servers:",
            "  fake:",
            "    enabled: true",
            "    transport: stdio",
            f"    command: {sys.executable}",
            "    args:",
            f"      - {fake_server}",
            f"    cwd: {target_file.parent}",
            "    env:",
            f"      PYTHONPATH: {Path(__file__).resolve().parents[2]}",
            "    timeout_seconds: 10",
            "    risk_level: read_only",
            "    allowed_tools:",
            "      - echo",
            "      - read_file",
            "      - list_directory",
        ]),
        encoding="utf-8",
    )
    return config_path


def test_load_external_mcp_config(tmp_path):
    target_file = tmp_path / "README.md"
    target_file.write_text("hello external mcp", encoding="utf-8")
    config_path = _write_config(tmp_path, target_file)

    configs = load_external_mcp_config(config_path)
    assert len(configs) == 1
    assert configs[0].name == "fake"
    assert configs[0].enabled is True
    assert configs[0].allowed_tools == ["echo", "read_file", "list_directory"]


def test_list_tools_filters_allowed_tools(tmp_path):
    target_file = tmp_path / "README.md"
    target_file.write_text("hello external mcp", encoding="utf-8")
    config_path = _write_config(tmp_path, target_file)

    tools = list_external_tools(str(config_path))
    public_names = {tool.public_name for tool in tools}

    assert "external_fake_echo" in public_names
    assert "external_fake_read_file" in public_names
    assert "external_fake_list_directory" in public_names
    assert "external_fake_delete_file" not in public_names


def test_call_external_tool(tmp_path, monkeypatch):
    target_file = tmp_path / "README.md"
    target_file.write_text("hello external mcp", encoding="utf-8")
    config_path = _write_config(tmp_path, target_file)
    monkeypatch.setenv("HPC_AGENT_EXTERNAL_MCP_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    result = call_external_tool(
        "external_fake_read_file",
        {"path": str(target_file)},
        config_path=str(config_path),
    )

    assert result["ok"] is True
    assert "hello external mcp" in result["message"]
    audit = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "external_fake_read_file" in audit


def test_doctor_external_mcp(tmp_path):
    target_file = tmp_path / "README.md"
    target_file.write_text("hello external mcp", encoding="utf-8")
    config_path = _write_config(tmp_path, target_file)

    result = doctor_external_mcp(str(config_path))

    assert result["ok"] is True
    assert result["servers"][0]["injected_tools"] == ["echo", "read_file", "list_directory"]


def test_agent_runtime_uses_external_mcp_tool(tmp_path, monkeypatch):
    target_file = tmp_path / "README.md"
    target_file.write_text("hello external mcp", encoding="utf-8")
    config_path = _write_config(tmp_path, target_file)
    monkeypatch.setenv("HPC_AGENT_EXTERNAL_MCP_CONFIG", str(config_path))
    monkeypatch.setenv("HPC_AGENT_EXTERNAL_MCP_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    result = execute_answer_intent(
        f"读取 {target_file}",
        "rag_qa",
        documents=[],
        sources=[],
        diagnoser=None,
        state=None,
    )

    assert result.handled is True
    assert result.intent == "external_mcp_tool"
    assert result.success is True
    assert "hello external mcp" in result.answer
    assert result.data["external_mcp"] is True
