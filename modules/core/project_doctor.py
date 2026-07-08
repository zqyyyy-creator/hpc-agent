from __future__ import annotations

import importlib
import importlib.metadata
import os
import tomllib
from pathlib import Path
from typing import Callable, Any

from modules.core.paths import DOCS_DIR, ENV_PATH, HPC_DOCUMENTS_DIR, MODULES_DIR, PROJECT_ROOT, SKILLS_DIR
from modules.core.environment_status import check_hpc_environment
from modules.skills.resource_detector import detect_available_resources
from modules.skills.skill_registry import load_skill_registry


def _ok_item(label: str, detail: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": True, "label": label, "detail": detail, "metadata": metadata or {}}


def _warn_item(label: str, detail: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ok": False, "label": label, "detail": detail, "metadata": metadata or {}}


def _path_status(path: Path, *, must_be_dir: bool = True) -> dict[str, Any]:
    if not path.exists():
        return _warn_item(str(path), "不存在", {"path": str(path)})
    if must_be_dir and not path.is_dir():
        return _warn_item(str(path), "存在但不是目录", {"path": str(path)})
    if not must_be_dir and not path.is_file():
        return _warn_item(str(path), "存在但不是文件", {"path": str(path)})
    return _ok_item(str(path), "存在", {"path": str(path)})


def _check_required_project_paths() -> dict[str, Any]:
    paths = [
        (ENV_PATH, False),
        (HPC_DOCUMENTS_DIR, True),
        (SKILLS_DIR, True),
        (DOCS_DIR, True),
        (MODULES_DIR, True),
    ]
    checks = [_path_status(path, must_be_dir=must_be_dir) for path, must_be_dir in paths]
    return {
        "success": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _check_env_summary() -> dict[str, Any]:
    required_vars = [
        "HPC_HOST",
        "HPC_USERNAME",
        "HPC_KEY_PATH",
        "HPC_REMOTE_WORKDIR",
        "PARATERA_BASE_URL",
        "PARATERA_API_KEY",
    ]
    optional_vars = [
        "PARATERA_MODEL",
        "HPC_DEFAULT_PARTITION",
        "HPC_VASP_PARTITION",
        "HPC_VASP_COMMAND",
        "HPC_CLAUDE_CODE_COMMAND",
        "HPC_VASP_REPORT_MODEL",
    ]
    missing_required = [name for name in required_vars if not os.getenv(name)]
    configured_optional = [name for name in optional_vars if os.getenv(name)]
    checks = [
        (
            _warn_item("Required env vars", f"缺少: {', '.join(missing_required)}")
            if missing_required
            else _ok_item("Required env vars", "关键变量已配置")
        ),
        _ok_item(
            "Optional env vars",
            f"已配置 {len(configured_optional)}/{len(optional_vars)}: {', '.join(configured_optional) or '-'}",
        ),
    ]
    return {
        "success": all(item["ok"] for item in checks),
        "checks": checks,
        "missing_required": missing_required,
        "configured_optional": configured_optional,
    }


def _check_package_entrypoint() -> dict[str, Any]:
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    checks: list[dict[str, Any]] = []
    try:
        if pyproject_path.is_file():
            data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
            scripts = data.get("project", {}).get("scripts", {})
            entrypoint = scripts.get("hpc-agent")
        else:
            scripts = {
                entry_point.name: entry_point.value
                for entry_point in importlib.metadata.entry_points(group="console_scripts")
                if entry_point.dist and entry_point.dist.metadata.get("Name") == "hpc-agent"
            }
            entrypoint = scripts.get("hpc-agent")
        if not entrypoint:
            checks.append(_warn_item("hpc-agent entrypoint", "未发现 hpc-agent console script"))
        elif ":" not in entrypoint:
            checks.append(_warn_item("hpc-agent entrypoint", f"{entrypoint} 不是 module:attr 格式"))
        else:
            module_name, attr_name = entrypoint.split(":", 1)
            module = importlib.import_module(module_name)
            attr = getattr(module, attr_name)
            checks.append(
                _ok_item(
                    "hpc-agent entrypoint",
                    f"{entrypoint} 可 import" + ("，可调用" if callable(attr) else "，但不可调用"),
                )
            )
            if not callable(attr):
                checks[-1] = _warn_item("hpc-agent entrypoint", f"{entrypoint} 存在但不可调用")
    except Exception as error:
        checks.append(_warn_item("hpc-agent entrypoint", f"{type(error).__name__}: {error}"))

    return {
        "success": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _check_rag_documents(
    documents: list[str] | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    try:
        if documents is None or sources is None:
            from modules.knowledge.knowledge_base import load_documents

            documents, sources = load_documents()
        source_files = sorted({source.split("#", 1)[0] for source in sources})
        checks = [
            _ok_item("RAG chunks", f"{len(documents)} chunks"),
            _ok_item("RAG source files", f"{len(source_files)} files: {', '.join(source_files[:8])}" + (" ..." if len(source_files) > 8 else "")),
        ]
        if not documents:
            checks[0] = _warn_item("RAG chunks", "未加载到任何 chunk")
        if not source_files:
            checks[1] = _warn_item("RAG source files", "未加载到任何 txt 文档")
        return {
            "success": all(item["ok"] for item in checks),
            "checks": checks,
            "chunk_count": len(documents),
            "source_files": source_files,
        }
    except Exception as error:
        source_files = sorted(path.name for path in HPC_DOCUMENTS_DIR.glob("*.txt"))
        checks = [
            (
                _ok_item("RAG source files", f"{len(source_files)} txt files")
                if source_files
                else _warn_item("RAG source files", "未找到任何 txt 文档")
            ),
            _warn_item("RAG chunks", f"{type(error).__name__}: {error}"),
        ]
        return {
            "success": False,
            "checks": checks,
            "chunk_count": 0,
            "source_files": source_files,
        }


def _check_skill_registry() -> dict[str, Any]:
    try:
        registry = load_skill_registry()
        handler_results = registry.validate_handlers()
        failed = [item for item in handler_results if item.get("ok") != "true"]
        skills = registry.all()
        checks = [
            _ok_item("Skill count", f"{len(skills)} skills"),
            _ok_item("Skill handlers", "全部 handler 可 import"),
        ]
        if not skills:
            checks[0] = _warn_item("Skill count", "未注册任何 skill")
        if failed:
            detail = "; ".join(f"{item['skill']}: {item['error']}" for item in failed[:5])
            checks[1] = _warn_item("Skill handlers", detail)
        return {
            "success": all(item["ok"] for item in checks),
            "checks": checks,
            "skills": [skill.name for skill in skills],
            "handler_results": handler_results,
        }
    except Exception as error:
        return {
            "success": False,
            "checks": [_warn_item("SkillRegistry", f"{type(error).__name__}: {error}")],
            "skills": [],
            "handler_results": [],
        }


def _check_local_resources() -> dict[str, Any]:
    try:
        resources = detect_available_resources()
        cpu = resources.get("cpu", {})
        memory = resources.get("memory", {})
        disk = resources.get("disk", {})
        gpu = resources.get("gpu", {})
        checks = [
            _ok_item("CPU", f"{cpu.get('logical_cores') or 'unknown'} logical cores"),
            _ok_item(
                "Memory",
                (
                    f"{memory.get('available_gb')} GB available / {memory.get('total_gb')} GB total"
                    if memory.get("total_gb") is not None
                    else "unknown"
                ),
            ),
            _ok_item("Disk", f"{disk.get('available_gb')} GB available / {disk.get('total_gb')} GB total"),
            _ok_item("GPU", f"{gpu.get('total_gpus', 0)} detected"),
        ]
        return {
            "success": True,
            "checks": checks,
            "resources": resources,
        }
    except Exception as error:
        return {
            "success": False,
            "checks": [_warn_item("Local resources", f"{type(error).__name__}: {error}")],
            "resources": {},
        }


def run_project_doctor(
    *,
    documents: list[str] | None = None,
    sources: list[str] | None = None,
    run_remote_command: Callable[[str], tuple[str, str]] | None = None,
) -> dict[str, Any]:
    sections = {
        "project_paths": _check_required_project_paths(),
        "env_summary": _check_env_summary(),
        "entrypoint": _check_package_entrypoint(),
        "hpc_environment": check_hpc_environment(run_remote_command=run_remote_command),
        "rag_documents": _check_rag_documents(documents, sources),
        "skill_registry": _check_skill_registry(),
        "local_resources": _check_local_resources(),
    }
    return {
        "success": all(section.get("success") for section in sections.values()),
        "sections": sections,
    }


def _format_check_line(item: dict[str, Any]) -> str:
    status = "OK" if item.get("ok") else "WARN"
    return f"- {status} {item.get('label')}: {item.get('detail')}"


def _format_section(title: str, section: dict[str, Any]) -> list[str]:
    lines = [title]
    lines.extend(_format_check_line(item) for item in section.get("checks", []))
    if section.get("remote_error"):
        lines.append(f"- WARN remote stderr/error: {section['remote_error']}")
    return lines


def format_project_doctor(result: dict[str, Any]) -> str:
    sections = result.get("sections", {})
    lines = [
        "HPC Agent 总体体检",
        "",
        "结论: " + ("主要组件看起来可用。" if result.get("success") else "存在 WARN 项，请优先处理。"),
        "",
    ]
    lines.extend(_format_section("1. 项目文件", sections.get("project_paths", {})))
    lines.append("")
    lines.extend(_format_section("2. .env 关键变量", sections.get("env_summary", {})))
    lines.append("")
    lines.extend(_format_section("3. 包入口", sections.get("entrypoint", {})))
    lines.append("")
    lines.extend(_format_section("4. SSH / 超算配置", sections.get("hpc_environment", {})))
    lines.append("")
    lines.extend(_format_section("5. RAG 文档", sections.get("rag_documents", {})))
    lines.append("")
    lines.extend(_format_section("6. Skills Registry", sections.get("skill_registry", {})))
    lines.append("")
    lines.extend(_format_section("7. 本地资源", sections.get("local_resources", {})))

    hpc_suggestions = sections.get("hpc_environment", {}).get("recovery_suggestions") or []
    if hpc_suggestions:
        lines.extend(["", "优先修复建议:"])
        for index, suggestion in enumerate(hpc_suggestions[:5], 1):
            lines.append(f"{index}. {suggestion['title']}: {suggestion['problem']}")

    return "\n".join(lines)
