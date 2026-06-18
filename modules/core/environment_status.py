from __future__ import annotations

import os
import shlex
import shutil
import stat
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


def _check_line(check: dict) -> str:
    return _status_line(check["ok"], check["label"], check["detail"])


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

    def add(ok: bool, label: str, detail: str, code: str, metadata: dict | None = None):
        checks.append({
            "ok": ok,
            "label": label,
            "detail": detail,
            "code": code,
            "metadata": metadata or {},
        })

    add(
        bool(os.getenv("PARATERA_BASE_URL")),
        "PARATERA_BASE_URL",
        os.getenv("PARATERA_BASE_URL") or "未配置",
        "api_config",
    )
    add(
        bool(os.getenv("PARATERA_API_KEY")),
        "PARATERA_API_KEY",
        _mask_secret(os.getenv("PARATERA_API_KEY")),
        "api_config",
    )
    add(
        bool(os.getenv("PARATERA_MODEL")),
        "PARATERA_MODEL",
        os.getenv("PARATERA_MODEL") or "未配置，将使用 DeepSeek-V4-Pro",
        "api_config",
    )
    add(bool(HOST), "HPC_HOST", HOST or "未配置", "required_env")
    add(bool(USERNAME), "HPC_USERNAME", USERNAME or "未配置", "required_env")

    key_path = Path(KEY_PATH).expanduser() if KEY_PATH else None
    key_ok, key_detail = _check_ssh_key(key_path)
    add(key_ok, "HPC_KEY_PATH", key_detail, "ssh_key", {"path": str(key_path) if key_path else ""})

    local_workdir = Path(os.getenv("HPC_LOCAL_WORKDIR", "~/hpc-local-jobs")).expanduser()
    add(
        _is_existing_writable_dir(local_workdir),
        "HPC_LOCAL_WORKDIR",
        _local_dir_detail(local_workdir),
        "local_dir",
        {"path": str(local_workdir)},
    )

    vasp_input = Path(VASP_LOCAL_JOBS_DIR).expanduser()
    vasp_output = Path(VASP_LOCAL_OUTPUT_DIR).expanduser()
    add(
        _is_existing_writable_dir(vasp_input),
        "HPC_LOCAL_VASP_JOBS_INPUT_DIR",
        _local_dir_detail(vasp_input),
        "local_dir",
        {"path": str(vasp_input)},
    )
    add(
        _is_existing_writable_dir(vasp_output),
        "HPC_LOCAL_VASP_JOBS_OUTPUT_DIR",
        _local_dir_detail(vasp_output),
        "local_dir",
        {"path": str(vasp_output)},
    )

    claude_command = os.getenv("HPC_CLAUDE_CODE_COMMAND", "claude").strip() or "claude"
    claude_ok, claude_detail = _check_local_command(claude_command)
    add(claude_ok, "HPC_CLAUDE_CODE_COMMAND", claude_detail, "claude_code", {"command": claude_command})

    remote_dirs = [
        ("HPC_REMOTE_WORKDIR", REMOTE_WORKDIR),
        ("HPC_VASP_REMOTE_INPUT_DIR", VASP_REMOTE_INPUT_DIR),
        ("HPC_VASP_REMOTE_OUTPUT_DIR", VASP_REMOTE_OUTPUT_DIR),
    ]

    missing_remote = [label for label, path in remote_dirs if not path]
    for label in missing_remote:
        add(False, label, "未配置", "remote_dir")

    remote_error = ""
    if run_remote_command is None:
        try:
            from modules.slurm.slurm_tools import run_remote_command as default_runner

            run_remote_command = default_runner
        except Exception as error:
            remote_error = f"{type(error).__name__}: {error}"

    configured_remote_dirs = [(label, path) for label, path in remote_dirs if path]
    vasp_command = os.getenv("HPC_VASP_COMMAND", "vasp_std").strip()
    vasp_setup_command = os.getenv("HPC_VASP_SETUP_COMMAND", "").strip()
    partitions = _configured_partitions()
    if run_remote_command and configured_remote_dirs:
        command = _build_remote_check_command(
            [path for _, path in configured_remote_dirs if path],
            vasp_command=vasp_command,
            vasp_setup_command=vasp_setup_command,
            partitions=partitions,
        )
        try:
            output, error = run_remote_command(command)
            remote_error = error.strip()
            remote_status = _parse_remote_check_output(output)
            for label, path in configured_remote_dirs:
                item = remote_status["dirs"].get(path, {})
                exists = item.get("exists") == "yes"
                writable = item.get("writable") == "yes"
                add(
                    exists and writable,
                    label,
                    f"{path} (exists={exists}, writable={writable})",
                    "remote_dir",
                    {"path": path, "exists": exists, "writable": writable},
                )

            vasp_item = remote_status["vasp_command"]
            if vasp_command:
                command_ok = vasp_item.get("ok") == "yes"
                detail = vasp_item.get("detail") or "远端未返回 VASP 命令检查结果"
                add(command_ok, "HPC_VASP_COMMAND", detail, "vasp_command", {"command": vasp_command})
            else:
                add(False, "HPC_VASP_COMMAND", "未配置", "vasp_command")

            if vasp_setup_command:
                setup_item = remote_status["vasp_setup"]
                setup_ok = setup_item.get("ok") == "yes"
                setup_detail = setup_item.get("detail") or "远端未返回 VASP setup 检查结果"
                add(setup_ok, "HPC_VASP_SETUP_COMMAND", setup_detail, "vasp_setup", {"command": vasp_setup_command})

            for partition_name in partitions:
                item = remote_status["partitions"].get(partition_name, {})
                status = item.get("status", "unknown")
                add(
                    status in {"yes", "unknown"},
                    f"partition:{partition_name}",
                    item.get("detail") or f"{partition_name} ({status})",
                    "partition",
                    {"partition": partition_name, "status": status},
                )
        except Exception as error:
            remote_error = f"{type(error).__name__}: {error}"
            for label, path in configured_remote_dirs:
                add(False, label, f"{path} (远端检查失败)", "remote_dir", {"path": path})
            if vasp_command:
                add(False, "HPC_VASP_COMMAND", "远端检查失败", "vasp_command", {"command": vasp_command})
            if vasp_setup_command:
                add(False, "HPC_VASP_SETUP_COMMAND", "远端检查失败", "vasp_setup", {"command": vasp_setup_command})
            for partition_name in partitions:
                add(False, f"partition:{partition_name}", "远端检查失败", "partition", {"partition": partition_name})

    result = {
        "success": all(item["ok"] for item in checks),
        "checks": checks,
        "remote_error": remote_error,
    }
    result["recovery_suggestions"] = build_config_recovery_suggestions(result)
    return result


def format_hpc_environment_check(result: dict) -> str:
    lines = ["超算配置体检", ""]
    lines.extend(_check_line(item) for item in result["checks"])

    if result.get("remote_error"):
        lines.extend(["", f"远端检查 stderr/错误: {result['remote_error']}"])

    lines.extend([
        "",
        "结论: " + ("配置看起来可用。" if result["success"] else "存在需要处理的配置项，请先修复 WARN 项。"),
    ])
    suggestions = result.get("recovery_suggestions") or build_config_recovery_suggestions(result)
    if suggestions:
        lines.extend(["", "修复建议:"])
        for index, suggestion in enumerate(suggestions, 1):
            lines.extend(_format_recovery_suggestion(index, suggestion))
    return "\n".join(lines)


def build_config_recovery_suggestions(result: dict) -> list[dict]:
    suggestions: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in result.get("checks", []):
        if item.get("ok"):
            continue
        suggestion = _suggestion_for_check(item)
        key = (suggestion["title"], suggestion["problem"])
        if key in seen:
            continue
        seen.add(key)
        suggestions.append(suggestion)
    return suggestions


def _format_recovery_suggestion(index: int, suggestion: dict) -> list[str]:
    lines = [
        f"{index}. {suggestion['title']}",
        f"   问题: {suggestion['problem']}",
        f"   影响: {suggestion['impact']}",
        "   建议:",
    ]
    lines.extend(f"   - {step}" for step in suggestion["steps"])
    return lines


def _suggestion_for_check(item: dict) -> dict:
    label = item.get("label", "")
    detail = item.get("detail", "")
    metadata = item.get("metadata", {})
    code = item.get("code", "")

    if code == "required_env":
        return {
            "title": f"补齐 {label}",
            "problem": f"{label} 未配置。",
            "impact": "Agent 无法建立到超算的 SSH 上下文，后续提交、监控和清理都会失败。",
            "steps": [
                f"在项目根目录 .env 中添加 {label}=实际值。",
                "保存后重启 TUI，让当前进程重新读取 .env。",
                "再次输入“检查我的超算配置”。",
            ],
        }
    if code == "api_config":
        return {
            "title": f"检查 Claude/API 配置 {label}",
            "problem": f"{label} 异常: {detail}",
            "impact": "Agent 的模型调用、Claude Code VASP 报告或知识问答可能不可用。",
            "steps": [
                "检查 .env 中 PARATERA_BASE_URL、PARATERA_API_KEY、PARATERA_MODEL 是否完整。",
                "确认 API Key 未过期，并且支持当前配置的模型。",
                "如果只影响 VASP 报告，还要检查 HPC_CLAUDE_CODE_MODEL 是否是网关支持的模型名。",
            ],
        }
    if code == "ssh_key":
        path = metadata.get("path") or "<你的私钥路径>"
        return {
            "title": "修复 SSH 私钥配置",
            "problem": f"HPC_KEY_PATH 异常: {detail}",
            "impact": "Agent 无法通过 SSH 登录超算，也就无法提交或读取作业。",
            "steps": [
                "确认 .env 中 HPC_KEY_PATH 指向本机私钥文件，而不是 .pub 公钥文件。",
                f"检查文件是否存在: realpath -e {shlex.quote(path)}",
                f"建议设置权限: chmod 600 {shlex.quote(path)}",
                "如果集群要求跳板机或密码登录，需要先把可用私钥配置好。",
            ],
        }
    if code == "local_dir":
        path = metadata.get("path") or detail
        return {
            "title": f"创建或修复本地目录 {label}",
            "problem": f"{label} 异常: {detail}",
            "impact": "Agent 无法保存本地输入、输出、作业记录或 VASP 分析结果。",
            "steps": [
                f"创建目录: mkdir -p {shlex.quote(path)}",
                f"确认当前用户可写: test -w {shlex.quote(path)}",
                "如果路径写错，修改 .env 后重启 TUI。",
            ],
        }
    if code == "remote_dir":
        path = metadata.get("path") or detail
        return {
            "title": f"创建或修复远端目录 {label}",
            "problem": f"{label} 异常: {detail}",
            "impact": "Agent 无法在远端上传脚本、写入 VASP 输入或保存运行输出。",
            "steps": [
                f"登录超算后创建目录: mkdir -p {shlex.quote(path)}",
                f"确认当前超算账号可写: test -w {shlex.quote(path)}",
                "如果目录位于错误文件系统，修改 .env 中对应的远端路径。",
            ],
        }
    if code == "vasp_command":
        command = metadata.get("command") or os.getenv("HPC_VASP_COMMAND", "vasp_std")
        return {
            "title": "修复 HPC_VASP_COMMAND",
            "problem": f"HPC_VASP_COMMAND 不可用: {detail}",
            "impact": "VASP 作业会提交成功但启动阶段失败，常见表现是 command not found 或 permission denied。",
            "steps": [
                f"登录超算后测试: {command}",
                "如果使用绝对路径，确认该文件存在且可执行，例如 test -x /path/to/vasp_std。",
                "如果依赖 module 或 source 环境，先修复 HPC_VASP_SETUP_COMMAND 或 HPC_VASP_MODULE。",
                "把 .env 中 HPC_VASP_COMMAND 改成集群真实可用的 VASP 启动命令。",
            ],
        }
    if code == "vasp_setup":
        command = metadata.get("command") or os.getenv("HPC_VASP_SETUP_COMMAND", "")
        return {
            "title": "修复 HPC_VASP_SETUP_COMMAND",
            "problem": f"HPC_VASP_SETUP_COMMAND 执行后环境仍不可用: {detail}",
            "impact": "VASP 依赖的 mpirun、动态库或编译器环境可能缺失，作业启动会失败。",
            "steps": [
                f"登录超算后执行 setup: {command}",
                "执行后检查: command -v mpirun",
                "再检查 VASP 命令中的可执行程序是否可找到或可执行。",
                "如果集群推荐 module load vasp/intelmpi，把对应命令写入 HPC_VASP_SETUP_COMMAND 或 HPC_VASP_MODULE。",
            ],
        }
    if code == "partition":
        partition = metadata.get("partition") or label.replace("partition:", "")
        return {
            "title": f"检查 partition {partition}",
            "problem": f"partition 配置异常: {detail}",
            "impact": "Slurm 可能拒绝提交，或作业长期 Pending。",
            "steps": [
                f"登录超算后查看分区: sinfo -p {shlex.quote(partition)}",
                "如果分区不存在，修改 HPC_DEFAULT_PARTITION 或 HPC_VASP_PARTITION。",
                "如果分区存在但不可用，换成当前账号有权限使用的 partition。",
            ],
        }
    if code == "claude_code":
        command = metadata.get("command") or "claude"
        return {
            "title": "修复 Claude Code 命令",
            "problem": f"HPC_CLAUDE_CODE_COMMAND 异常: {detail}",
            "impact": "VASP 一键分析中的 Claude Code 报告生成会失败，但普通提交和同步不受影响。",
            "steps": [
                f"本地检查命令: command -v {shlex.quote(command.split()[0])}",
                "如果没有安装 Claude Code，请安装后把可执行命令写入 HPC_CLAUDE_CODE_COMMAND。",
                "如果命令在自定义路径，使用绝对路径配置。",
            ],
        }
    return {
        "title": f"检查 {label}",
        "problem": f"{label} 异常: {detail}",
        "impact": "相关功能可能不可用。",
        "steps": ["按上面的 WARN 详情检查 .env、文件路径和远端权限。"],
    }


def _can_create_parent(path: Path) -> bool:
    parent = path.parent
    return parent.exists() and os.access(parent, os.W_OK)


def _is_existing_writable_dir(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def _local_dir_detail(path: Path) -> str:
    if path.is_dir():
        return f"{path} (writable={os.access(path, os.W_OK)})"
    if path.exists():
        return f"{path} (存在但不是目录)"
    parent_state = "parent_writable=yes" if _can_create_parent(path) else "parent_writable=no"
    return f"{path} (不存在, {parent_state})"


def _check_ssh_key(path: Path | None) -> tuple[bool, str]:
    if not path:
        return False, "未配置"
    if not path.exists():
        return False, f"{path} (不存在)"
    if not path.is_file():
        return False, f"{path} (不是文件)"
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return False, f"{path} (权限 {oct(mode)} 过宽，建议 0o600)"
    return True, f"{path} (权限 {oct(mode)})"


def _check_local_command(command: str) -> tuple[bool, str]:
    executable = command.split()[0] if command else ""
    if not executable:
        return False, "未配置"
    path = Path(executable).expanduser()
    if path.is_absolute() or "/" in executable:
        return path.is_file() and os.access(path, os.X_OK), f"{path} (executable={path.is_file() and os.access(path, os.X_OK)})"
    resolved = shutil.which(executable)
    return bool(resolved), resolved or f"{executable} 不在 PATH 中"


def _configured_partitions() -> list[str]:
    values = []
    for value in [DEFAULT_PARTITION, VASP_PARTITION]:
        if value and value not in values:
            values.append(value)
    return values


def _build_remote_check_command(
    paths: list[str],
    *,
    vasp_command: str = "",
    vasp_setup_command: str = "",
    partitions: list[str] | None = None,
) -> str:
    quoted_paths = " ".join(shlex.quote(path) for path in paths)
    command = (
        "for d in "
        + quoted_paths
        + "; do "
        "exists=no; writable=no; "
        "[ -d \"$d\" ] && exists=yes; "
        "[ -w \"$d\" ] && writable=yes; "
        "printf 'DIR\\t%s\\t%s\\t%s\\n' \"$d\" \"$exists\" \"$writable\"; "
        "done"
    )
    if vasp_command:
        command += "; " + _build_vasp_remote_check(vasp_command, vasp_setup_command)
    for partition in partitions or []:
        command += "; " + _build_partition_remote_check(partition)
    return command


def _parse_remote_check_output(output: str) -> dict:
    result = {
        "dirs": {},
        "vasp_command": {},
        "vasp_setup": {},
        "partitions": {},
    }
    for line in output.splitlines():
        if line.startswith("DIR\t"):
            _, path, exists, writable = line.split("\t", 3)
            result["dirs"][path] = {"exists": exists, "writable": writable}
            continue
        if line.startswith("VASP_COMMAND\t"):
            _, ok, detail = line.split("\t", 2)
            result["vasp_command"] = {"ok": ok, "detail": detail}
            continue
        if line.startswith("VASP_SETUP\t"):
            _, ok, detail = line.split("\t", 2)
            result["vasp_setup"] = {"ok": ok, "detail": detail}
            continue
        if line.startswith("PARTITION\t"):
            _, name, status, detail = line.split("\t", 3)
            result["partitions"][name] = {"status": status, "detail": detail}
            continue
    return result


def _build_vasp_remote_check(vasp_command: str, setup_command: str) -> str:
    vasp = shlex.quote(vasp_command)
    setup = shlex.quote(setup_command)
    return (
        f"vasp_cmd={vasp}; setup_cmd={setup}; "
        "first=$(printf '%s\\n' \"$vasp_cmd\" | awk '{print $1}'); "
        "abs=$(printf '%s\\n' \"$vasp_cmd\" | awk '{for (i=1;i<=NF;i++) if ($i ~ /^\\//) {print $i; exit}}'); "
        "setup_ok=yes; mpirun_ok=unknown; first_ok=no; abs_ok=yes; "
        "if [ -n \"$setup_cmd\" ]; then bash -lc \"$setup_cmd >/dev/null 2>&1\" || setup_ok=no; fi; "
        "if [ -n \"$setup_cmd\" ]; then bash -lc \"$setup_cmd >/dev/null 2>&1; command -v mpirun >/dev/null 2>&1\" && mpirun_ok=yes || mpirun_ok=no; "
        "else command -v mpirun >/dev/null 2>&1 && mpirun_ok=yes || mpirun_ok=no; fi; "
        "if [ -n \"$setup_cmd\" ]; then bash -lc \"$setup_cmd >/dev/null 2>&1; command -v \\\"$first\\\" >/dev/null 2>&1\" && first_ok=yes || first_ok=no; "
        "else command -v \"$first\" >/dev/null 2>&1 && first_ok=yes || first_ok=no; fi; "
        "if [ -n \"$abs\" ] && [ ! -x \"$abs\" ]; then abs_ok=no; fi; "
        "overall=no; [ \"$setup_ok\" = yes ] && [ \"$first_ok\" = yes ] && [ \"$abs_ok\" = yes ] && overall=yes; "
        "printf 'VASP_COMMAND\\t%s\\tcmd=%s first=%s first_ok=%s abs=%s abs_ok=%s\\n' \"$overall\" \"$vasp_cmd\" \"$first\" \"$first_ok\" \"$abs\" \"$abs_ok\"; "
        "setup_overall=yes; [ \"$setup_ok\" = yes ] && [ \"$mpirun_ok\" != no ] && setup_overall=yes || setup_overall=no; "
        "printf 'VASP_SETUP\\t%s\\tsetup_ok=%s mpirun_ok=%s\\n' \"$setup_overall\" \"$setup_ok\" \"$mpirun_ok\""
    )


def _build_partition_remote_check(partition: str) -> str:
    quoted = shlex.quote(partition)
    return (
        f"part={quoted}; "
        "if command -v sinfo >/dev/null 2>&1; then "
        "sinfo -h -p \"$part\" >/dev/null 2>&1 && "
        "printf 'PARTITION\\t%s\\tyes\\t%s exists\\n' \"$part\" \"$part\" || "
        "printf 'PARTITION\\t%s\\tno\\t%s not found or not available\\n' \"$part\" \"$part\"; "
        "else printf 'PARTITION\\t%s\\tunknown\\tsinfo unavailable, cannot verify partition\\n' \"$part\"; fi"
    )
