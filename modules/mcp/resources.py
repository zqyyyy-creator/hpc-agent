from __future__ import annotations

import json
from pathlib import Path

from modules.core.environment_status import check_hpc_environment
from modules.core.paths import DOCS_DIR, HPC_DOCUMENTS_DIR
from modules.mcp.audit import audit_path
from modules.mcp.formatters import scrub_secrets
from modules.skills.skill_registry import load_skill_registry
from modules.slurm.job_registry import list_jobs


def read_text_file(path: Path, *, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fallback


def user_guide() -> str:
    return read_text_file(DOCS_DIR / "USER_GUIDE.md", fallback="USER_GUIDE.md not found.")


def cluster_info() -> str:
    parts: list[str] = []
    for path in sorted(HPC_DOCUMENTS_DIR.glob("*.txt")):
        parts.append(f"# {path.name}\n\n{read_text_file(path)}")
    return "\n\n---\n\n".join(parts) or "No cluster documents found."


def skills_json() -> str:
    registry = load_skill_registry()
    payload = {
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "type": skill.type,
                "intents": list(skill.intents),
                "triggers": list(skill.triggers),
                "risk": skill.risk,
                "source": skill.source,
                "handler": skill.handler,
                "runtime": dict(skill.runtime),
                "path": str(skill.path),
            }
            for skill in sorted(registry.all(), key=lambda item: (item.source, item.name))
        ],
        "skipped": [
            {
                "name": item.name,
                "path": str(item.path),
                "reason": item.reason,
                "source": item.source,
            }
            for item in registry.skipped()
        ],
    }
    return json.dumps(scrub_secrets(payload), ensure_ascii=False, indent=2)


def config_status_json() -> str:
    return json.dumps(scrub_secrets(check_hpc_environment()), ensure_ascii=False, indent=2)


def recent_jobs_json(limit: int = 10) -> str:
    jobs = list_jobs()
    items = sorted(
        [
            {"job_id": str(job_id), **dict(metadata or {})}
            for job_id, metadata in jobs.items()
        ],
        key=lambda item: str(item.get("updated_at") or item.get("registered_at") or ""),
        reverse=True,
    )[:limit]
    return json.dumps(scrub_secrets({"jobs": items, "count": len(items)}), ensure_ascii=False, indent=2)


def capabilities_json() -> str:
    payload = {
        "service": "hpc-agent-mcp",
        "schema_version": "2026-07-13",
        "transports": ["stdio", "streamable-http"],
        "primary_tool": "hpc_agent_chat",
        "structured_tools": [
            "hpc_generate_sbatch_structured",
            "hpc_prepare_vasp_job_structured",
            "vasp_generate_inputs_structured",
            "vasp_analyze_local_result_structured",
            "vasp_sync_output_structured",
            "hpc_submit_prepared_job",
            "hpc_query_job_structured",
            "hpc_prepare_cleanup_structured",
            "hpc_execute_cleanup",
        ],
        "domains": ["Slurm", "VASP", "HPC 配置", "作业日志", "集群知识"],
        "risk_levels": ["read_only", "write_preview", "write_local", "write_execute", "destructive_preview", "destructive"],
        "guards": {
            "write_execute": "需要 confirm=true 且服务端设置 HPC_AGENT_MCP_ENABLE_WRITE=1。",
            "destructive": "需要 confirm=true 且服务端设置 HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1。",
        },
        "recommended_client_behavior": [
            "普通对话和依赖上下文的请求优先使用 hpc_agent_chat。",
            "当参数已经明确且不希望再解析自然语言时，使用结构化工具。",
            "启用写入或危险操作前，先读取 hpc-agent://security/policy。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tool_schema_json() -> str:
    payload = {
        "schema_version": "2026-07-13",
        "response_envelope": {
            "ok": "布尔成功标记",
            "risk": "read_only | write_preview | write_local | write_execute | destructive_preview | destructive",
            "message": "完整可读输出",
            "reply": "可选的简短助手回复",
            "plain_text": "简单客户端最兼容的文本字段",
            "data": "包含工具专属字段的结构化数据",
            "next_step": "可选下一步建议",
            "requires_confirmation": "执行前是否需要用户/客户端确认",
            "required_env": "受保护执行所需的可选环境变量",
            "schema_version": "返回结构版本",
        },
        "tools": {
            "hpc_agent_chat": {
                "input": {"message": "string", "confirm": "boolean default false"},
                "use_when": "自然语言请求、最近作业引用、提交上一个预览、诊断、配置检查、Slurm/VASP 工作流。",
            },
            "hpc_generate_sbatch_structured": {
                "input": {
                    "command": "必填字符串",
                    "nodes": "整数，默认 1",
                    "time_limit": "HH:MM:SS 字符串，默认 00:10:00",
                    "partition": "可选字符串",
                    "cpus_per_task": "整数，默认 1",
                    "job_name": "字符串，默认 hpc_agent_job",
                    "memory": "可选字符串，例如 8G",
                    "gpu_count": "可选整数",
                },
                "risk": "write_preview",
            },
            "hpc_submit_prepared_job": {
                "input": {"script": "string", "submission_kind": "slurm|vasp", "confirm": "boolean"},
                "risk": "write_execute",
                "guard": "HPC_AGENT_MCP_ENABLE_WRITE=1",
            },
            "hpc_prepare_vasp_job_structured": {
                "input": {
                    "local_input_dir": "必填字符串",
                    "partition": "可选字符串",
                    "nodes": "整数，默认 1",
                    "time_limit": "HH:MM:SS 字符串，默认 01:00:00",
                    "job_name": "可选字符串",
                    "vasp_command": "可选字符串",
                    "setup_command": "可选字符串",
                },
                "risk": "write_preview",
            },
            "vasp_generate_inputs_structured": {
                "input": {
                    "job_name": "必填字符串",
                    "element": "可选字符串，例如 Si",
                    "formula": "可选字符串，例如 Si2",
                    "calculation_type": "字符串，默认 static",
                    "encut": "可选整数",
                    "kpoints": "可选的三个整数数组，例如 [2, 2, 2]",
                    "jobs_dir": "可选字符串",
                    "description": "可选字符串",
                    "overwrite": "布尔值，默认 false",
                },
                "risk": "write_local",
            },
            "vasp_analyze_local_result_structured": {
                "input": {"local_job_dir": "必填字符串"},
                "risk": "write_local",
            },
            "vasp_sync_output_structured": {
                "input": {"job_id": "必填字符串", "confirm": "布尔值，默认 false"},
                "risk": "write_execute",
                "guard": "HPC_AGENT_MCP_ENABLE_WRITE=1",
            },
            "hpc_query_job_structured": {
                "input": {"job_id": "string", "query_type": "status|output|error|detail"},
                "risk": "read_only",
            },
            "hpc_prepare_cleanup_structured": {
                "input": {
                    "cleanup_type": "job|all_jobs|vasp_job|all_vasp_jobs",
                    "job_id": "string optional",
                    "selector": "string optional",
                    "scope": "all|input|output|input_and_output",
                },
                "risk": "destructive_preview",
            },
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def deployment_status_json() -> str:
    payload = {
        "service": "hpc-agent-mcp",
        "health_endpoint": "/health",
        "mcp_default_path": "/mcp",
        "audit_log": str(audit_path()),
        "log_dir_env": "HPC_AGENT_LOG_DIR",
        "allowed_host_env": "HPC_AGENT_MCP_ALLOWED_HOST",
        "write_enabled_env": "HPC_AGENT_MCP_ENABLE_WRITE",
        "destructive_enabled_env": "HPC_AGENT_MCP_ENABLE_DESTRUCTIVE",
    }
    return json.dumps(scrub_secrets(payload), ensure_ascii=False, indent=2)


def security_policy_json() -> str:
    payload = {
        "default_policy": "先预览，确认后执行",
        "secrets": "API key、token、password 和类似私钥的字段会从 MCP payload 中脱敏。",
        "write_execute": {
            "tools": ["hpc_submit_prepared_job", "vasp_sync_output"],
            "requires": ["confirm=true", "HPC_AGENT_MCP_ENABLE_WRITE=1"],
        },
        "destructive": {
            "tools": ["hpc_execute_cleanup"],
            "requires": ["confirm=true", "HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1", "已有清理预览"],
        },
        "audit": {
            "enabled_for": ["write_preview", "write_local", "write_execute", "destructive_preview", "destructive"],
            "path": str(audit_path()),
        },
    }
    return json.dumps(scrub_secrets(payload), ensure_ascii=False, indent=2)


def examples_json() -> str:
    payload = {
        "natural_language": [
            {"tool": "hpc_agent_chat", "arguments": {"message": "检查当前 HPC 配置"}},
            {"tool": "hpc_agent_chat", "arguments": {"message": "查刚才那个作业"}},
        ],
        "structured": [
            {
                "tool": "hpc_generate_sbatch_structured",
                "arguments": {
                    "command": "hostname",
                    "nodes": 1,
                    "time_limit": "00:05:00",
                    "partition": "amd_test",
                    "cpus_per_task": 1,
                    "job_name": "hostname_test",
                },
            },
            {"tool": "hpc_query_job_structured", "arguments": {"job_id": "12345", "query_type": "status"}},
            {
                "tool": "hpc_prepare_vasp_job_structured",
                "arguments": {
                    "local_input_dir": "/home/qyz/vasp-jobs-input/si_static_test",
                    "nodes": 1,
                    "time_limit": "01:00:00",
                    "partition": "amd_test",
                },
            },
            {
                "tool": "vasp_generate_inputs_structured",
                "arguments": {
                    "job_name": "si_static_test",
                    "element": "Si",
                    "calculation_type": "static",
                    "encut": 400,
                    "kpoints": [2, 2, 2],
                },
            },
            {
                "tool": "vasp_analyze_local_result_structured",
                "arguments": {"local_job_dir": "/home/qyz/vasp-jobs-output/si_static_test"},
            },
        ],
        "guarded": [
            {
                "tool": "hpc_submit_prepared_job",
                "arguments": {"script": "#!/bin/bash\nhostname\n", "submission_kind": "slurm", "confirm": True},
                "requires_env": "HPC_AGENT_MCP_ENABLE_WRITE=1",
            }
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
