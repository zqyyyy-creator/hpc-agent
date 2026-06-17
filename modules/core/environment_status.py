from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from modules.core.hpc_config import (
    DEFAULT_PARTITION,
    HOST,
    KEY_PATH,
    REMOTE_WORKDIR,
    USERNAME,
    VASP_LOCAL_JOBS_DIR,
    VASP_LOCAL_OUTPUT_DIR,
    VASP_PARTITION,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
)


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _mask_secret(value: str | None) -> str:
    if not value:
        return "<未配置>"
    return "<已配置>"


def _status_line(ok: bool, label: str, detail: str) -> str:
    status = "OK" if ok else "WARN"
    return f"- {status} {label}: {detail}"


def format_current_model_and_config() -> str:
    paratera_model = os.getenv("PARATERA_MODEL", "DeepSeek-V4-Pro")
    claude_model = os.getenv("HPC_CLAUDE_CODE_MODEL", "DeepSeek-V4-Pro")
    base_url = os.getenv("PARATERA_BASE_URL") or "<未配置>"

    return "\n".join([
        "当前 Agent 配置",
        "",
        f"Agent 主体模型: {paratera_model}",
        f"Claude Code VASP 报告模型: {claude_model}",
        f"LLM 网关: {base_url}",
        f"API Key: {_mask_secret(os.getenv('PARATERA_API_KEY'))}",
        "",
        f"超算主机: {HOST or '<未配置>'}",
        f"超算用户名: {USERNAME or '<未配置>'}",
        f"SSH 私钥: {KEY_PATH or '<未配置>'}",
        f"普通作业本地目录: {Path(os.getenv('HPC_LOCAL_WORKDIR', '~/hpc-local-jobs')).expanduser()}",
        f"普通作业远端目录: {REMOTE_WORKDIR or '<未配置>'}",
        f"普通作业默认 partition: {DEFAULT_PARTITION or '<集群默认>'}",
        f"VASP 本地输入目录: {Path(VASP_LOCAL_JOBS_DIR).expanduser()}",
        f"VASP 本地输出目录: {Path(VASP_LOCAL_OUTPUT_DIR).expanduser()}",
        f"VASP 远端输入目录: {VASP_REMOTE_INPUT_DIR or '<未配置>'}",
        f"VASP 远端输出目录: {VASP_REMOTE_OUTPUT_DIR or '<未配置>'}",
        f"VASP 默认 partition: {VASP_PARTITION or '<集群默认>'}",
    ])


def check_hpc_environment(
    *,
    run_remote_command: Callable[[str], tuple[str, str]] | None = None,
) -> dict:
    checks: list[dict] = []

    def add(ok: bool, label: str, detail: str):
        checks.append({"ok": ok, "label": label, "detail": detail})

    add(bool(os.getenv("PARATERA_BASE_URL")), "PARATERA_BASE_URL", os.getenv("PARATERA_BASE_URL") or "未配置")
    add(bool(os.getenv("PARATERA_API_KEY")), "PARATERA_API_KEY", _mask_secret(os.getenv("PARATERA_API_KEY")))
    add(bool(os.getenv("PARATERA_MODEL")), "PARATERA_MODEL", os.getenv("PARATERA_MODEL") or "未配置，将使用 DeepSeek-V4-Pro")
    add(bool(HOST), "HPC_HOST", HOST or "未配置")
    add(bool(USERNAME), "HPC_USERNAME", USERNAME or "未配置")

    key_path = Path(KEY_PATH).expanduser() if KEY_PATH else None
    add(bool(key_path and key_path.is_file()), "HPC_KEY_PATH", str(key_path) if key_path else "未配置")

    local_workdir = Path(os.getenv("HPC_LOCAL_WORKDIR", "~/hpc-local-jobs")).expanduser()
    add(local_workdir.exists() or _can_create_parent(local_workdir), "HPC_LOCAL_WORKDIR", str(local_workdir))

    vasp_input = Path(VASP_LOCAL_JOBS_DIR).expanduser()
    vasp_output = Path(VASP_LOCAL_OUTPUT_DIR).expanduser()
    add(vasp_input.exists() or _can_create_parent(vasp_input), "HPC_LOCAL_VASP_JOBS_INPUT_DIR", str(vasp_input))
    add(vasp_output.exists() or _can_create_parent(vasp_output), "HPC_LOCAL_VASP_JOBS_OUTPUT_DIR", str(vasp_output))

    remote_dirs = [
        ("HPC_REMOTE_WORKDIR", REMOTE_WORKDIR),
        ("HPC_VASP_REMOTE_INPUT_DIR", VASP_REMOTE_INPUT_DIR),
        ("HPC_VASP_REMOTE_OUTPUT_DIR", VASP_REMOTE_OUTPUT_DIR),
    ]

    missing_remote = [label for label, path in remote_dirs if not path]
    for label in missing_remote:
        add(False, label, "未配置")

    remote_error = ""
    if run_remote_command is None:
        try:
            from modules.slurm.slurm_tools import run_remote_command as default_runner

            run_remote_command = default_runner
        except Exception as error:
            remote_error = f"{type(error).__name__}: {error}"

    configured_remote_dirs = [(label, path) for label, path in remote_dirs if path]
    if run_remote_command and configured_remote_dirs:
        command = _build_remote_check_command([path for _, path in configured_remote_dirs if path])
        try:
            output, error = run_remote_command(command)
            remote_error = error.strip()
            remote_status = _parse_remote_check_output(output)
            for label, path in configured_remote_dirs:
                item = remote_status.get(path, {})
                exists = item.get("exists") == "yes"
                writable = item.get("writable") == "yes"
                add(exists and writable, label, f"{path} (exists={exists}, writable={writable})")
        except Exception as error:
            remote_error = f"{type(error).__name__}: {error}"
            for label, path in configured_remote_dirs:
                add(False, label, f"{path} (远端检查失败)")

    return {
        "success": all(item["ok"] for item in checks),
        "checks": checks,
        "remote_error": remote_error,
    }


def format_hpc_environment_check(result: dict) -> str:
    lines = ["超算配置体检", ""]
    lines.extend(_status_line(item["ok"], item["label"], item["detail"]) for item in result["checks"])

    if result.get("remote_error"):
        lines.extend(["", f"远端检查 stderr/错误: {result['remote_error']}"])

    lines.extend([
        "",
        "结论: " + ("配置看起来可用。" if result["success"] else "存在需要处理的配置项，请先修复 WARN 项。"),
    ])
    return "\n".join(lines)


def _can_create_parent(path: Path) -> bool:
    parent = path.parent
    return parent.exists() and os.access(parent, os.W_OK)


def _build_remote_check_command(paths: list[str]) -> str:
    quoted_paths = " ".join(shlex.quote(path) for path in paths)
    return (
        "for d in "
        + quoted_paths
        + "; do "
        "exists=no; writable=no; "
        "[ -d \"$d\" ] && exists=yes; "
        "[ -w \"$d\" ] && writable=yes; "
        "printf 'DIR\\t%s\\t%s\\t%s\\n' \"$d\" \"$exists\" \"$writable\"; "
        "done"
    )


def _parse_remote_check_output(output: str) -> dict:
    result = {}
    for line in output.splitlines():
        if not line.startswith("DIR\t"):
            continue
        _, path, exists, writable = line.split("\t", 3)
        result[path] = {"exists": exists, "writable": writable}
    return result
