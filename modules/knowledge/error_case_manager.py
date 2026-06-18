from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REAL_CASES_PATH = Path("data/errors/real_cases.json")
REQUIRED_REAL_CASE_FIELDS = {
    "id",
    "domain",
    "title",
    "severity",
    "applies_to",
    "confidence",
    "patterns",
    "evidence",
    "reason",
    "suggestions",
    "commands",
    "prevention",
}
ALLOWED_SEVERITIES = {"info", "warning", "error"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
DOMAIN_PREFIXES = {
    "vasp": "VASP",
    "slurm": "SLURM",
    "config": "CONFIG",
    "claude": "CLAUDE",
    "sync": "SYNC",
    "tui": "TUI",
    "agent": "AGENT",
    "python": "PYTHON",
    "storage": "STORAGE",
    "environment": "ENV",
}
CASE_DRAFT_TRIGGERS = [
    "把这个错误整理成案例",
    "把这个报错整理成案例",
    "生成案例草稿",
    "加入错误案例库",
    "添加到错误案例库",
    "收录错误",
    "收录这个错误",
    "整理成错误案例",
    "整理成案例",
]


def load_real_cases(path: str | Path = REAL_CASES_PATH) -> list[dict[str, Any]]:
    case_path = Path(path)
    if not case_path.exists():
        return []
    return json.loads(case_path.read_text(encoding="utf-8"))


def write_real_cases(cases: list[dict[str, Any]], path: str | Path = REAL_CASES_PATH):
    case_path = Path(path)
    case_path.parent.mkdir(parents=True, exist_ok=True)
    case_path.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_real_case(case: dict[str, Any], existing_cases: list[dict[str, Any]] | None = None):
    missing = REQUIRED_REAL_CASE_FIELDS - set(case)
    if missing:
        return False, f"案例缺少字段: {', '.join(sorted(missing))}"

    if case["severity"] not in ALLOWED_SEVERITIES:
        return False, f"severity 只能是: {', '.join(sorted(ALLOWED_SEVERITIES))}"

    if case["confidence"] not in ALLOWED_CONFIDENCE:
        return False, f"confidence 只能是: {', '.join(sorted(ALLOWED_CONFIDENCE))}"

    for field in ["patterns", "evidence", "suggestions", "commands", "applies_to"]:
        if not isinstance(case.get(field), list) or not case[field]:
            return False, f"{field} 必须是非空列表"

    for field in ["id", "domain", "title", "reason", "prevention"]:
        if not isinstance(case.get(field), str) or not case[field].strip():
            return False, f"{field} 必须是非空字符串"

    if existing_cases and any(item.get("id") == case["id"] for item in existing_cases):
        return False, f"案例 ID 已存在: {case['id']}"

    return True, ""


def append_real_case(case: dict[str, Any], path: str | Path = REAL_CASES_PATH) -> dict[str, Any]:
    cases = load_real_cases(path)
    ok, error = validate_real_case(case, cases)
    if not ok:
        return {
            "success": False,
            "message": f"没有写入错误案例库: {error}",
            "case": case,
        }

    cases.append(case)
    write_real_cases(cases, path)
    return {
        "success": True,
        "message": (
            "已加入错误案例库。\n\n"
            f"案例 ID: {case['id']}\n"
            f"标题: {case['title']}\n"
            f"文件: {Path(path)}"
        ),
        "case": case,
        "path": str(path),
    }


def build_error_case_draft(
    request_text: str,
    *,
    state=None,
    diagnoser=None,
    path: str | Path = REAL_CASES_PATH,
) -> dict[str, Any]:
    source_log = _extract_source_log(request_text, state=state)
    if not source_log:
        return {
            "success": False,
            "message": (
                "没有找到可整理的错误日志。\n\n"
                "可以这样使用：\n"
                "把这个错误整理成案例：Missing required VASP input file: POTCAR\n\n"
                "或者先粘贴/诊断错误日志，再输入“把这个错误整理成案例”。"
            ),
        }

    if diagnoser:
        existing_matches = [
            item
            for item in diagnoser.diagnose(source_log)
            if item.get("source") == "real_case"
        ]
        if existing_matches:
            matched = existing_matches[0]
            return {
                "success": False,
                "message": (
                    "这个错误已经命中真实案例库，不需要重复添加。\n\n"
                    f"已命中: {matched.get('id')} - {matched.get('name')}"
                ),
                "matched_case": matched,
            }

    case = _draft_case_from_log(source_log, diagnoser=diagnoser, existing_cases=load_real_cases(path))
    preview = format_error_case_draft(case, source_log)
    return {
        "success": True,
        "message": preview,
        "case": case,
        "source_log": source_log,
        "pending_action": {
            "kind": "add_error_case",
            "payload": {
                "case": case,
                "path": str(path),
            },
            "description": "错误案例草稿，回复“确认”后写入 data/errors/real_cases.json。",
        },
    }


def format_error_case_draft(case: dict[str, Any], source_log: str) -> str:
    case_json = json.dumps(case, ensure_ascii=False, indent=2)
    excerpt = _redact_sensitive_text(source_log.strip())
    if len(excerpt) > 800:
        excerpt = excerpt[:800].rstrip() + "..."

    return "\n".join([
        "已生成错误案例草稿，尚未写入文件。",
        "",
        "来源日志摘录:",
        excerpt,
        "",
        "案例草稿:",
        "```json",
        case_json,
        "```",
        "",
        "确认写入请回复“确认”；取消请回复“取消”。",
    ])


def _extract_source_log(request_text: str, *, state=None) -> str:
    direct = _strip_case_draft_trigger(request_text).strip()
    if _looks_like_error_log(direct):
        return direct

    if not state:
        return ""

    for turn in reversed(getattr(state, "conversation_turns", [])[:-1]):
        if turn.get("role") != "user":
            continue
        content = str(turn.get("content", "")).strip()
        if not content or _is_case_draft_request(content):
            continue
        if _looks_like_error_log(content):
            return content

    return ""


def _strip_case_draft_trigger(text: str) -> str:
    stripped = str(text).strip()
    for trigger in CASE_DRAFT_TRIGGERS:
        stripped = stripped.replace(trigger, "")
    stripped = re.sub(r"^[：:\s，,。；;]+", "", stripped)
    return stripped


def _is_case_draft_request(text: str) -> bool:
    normalized = str(text).replace(" ", "").lower()
    return any(trigger.replace(" ", "").lower() in normalized for trigger in CASE_DRAFT_TRIGGERS)


def _looks_like_error_log(text: str) -> bool:
    if not text or len(text.strip()) < 8:
        return False
    lowered = text.lower()
    markers = [
        "error", "failed", "failure", "exception", "traceback",
        "not found", "permission denied", "out of memory", "oom",
        "time limit", "unauthorized", "invalid", "missing",
        "报错", "错误", "失败", "缺少", "找不到", "不可用",
        "权限", "未配置", "同步文件数: 0",
    ]
    return any(marker in lowered or marker in text for marker in markers)


def _draft_case_from_log(
    source_log: str,
    *,
    diagnoser=None,
    existing_cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generic_match = None
    if diagnoser:
        for result in diagnoser.diagnose(source_log):
            if result.get("source") != "real_case":
                generic_match = result
                break

    domain = _infer_domain(source_log, generic_match)
    title = _infer_title(source_log, domain, generic_match)
    severity = _infer_severity(source_log, generic_match)
    applies_to = _infer_applies_to(source_log, domain)
    patterns = _extract_patterns(source_log)
    commands = _suggest_commands(domain, source_log)
    reason = (
        generic_match.get("reason")
        if generic_match
        else "这是从真实日志整理出的新错误案例。具体原因需要结合上下文确认。"
    )
    suggestions = _suggestions_from_match(generic_match) or _suggestions_for_domain(domain)

    return {
        "id": _next_case_id(domain, existing_cases or []),
        "domain": domain,
        "title": title,
        "severity": severity,
        "applies_to": applies_to,
        "confidence": "medium",
        "patterns": patterns,
        "evidence": [
            "用户提供的真实错误日志可稳定命中该模式",
            "该案例由 Agent 生成草稿，写入前已由用户确认",
        ],
        "reason": reason,
        "suggestions": suggestions,
        "commands": commands,
        "prevention": "再次遇到类似日志时，优先按本案例的排查命令确认上下文，再决定是否调整配置或重新提交。",
    }


def _infer_domain(text: str, generic_match: dict | None) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["vasp", "potcar", "poscar", "outcar", "oszicar", "incar", "kpoints"]):
        return "vasp"
    if any(token in lowered for token in ["sftp", "ssh", "channel closed", "connection reset"]):
        return "sync"
    if any(token in lowered for token in ["claude", "paratera", "api key", "unauthorized", "authentication"]):
        return "claude"
    if any(token in lowered for token in ["clipboard", "pyperclip", "xclip", "wl-copy"]) or "剪贴板" in text:
        return "tui"
    if any(token in lowered for token in ["sbatch", "squeue", "sacct", "slurm", "partition"]):
        return "slurm"
    if any(token in text for token in ["未配置", ".env", "HPC_"]):
        return "config"
    if generic_match:
        category = str(generic_match.get("category", "")).lower()
        if category in DOMAIN_PREFIXES:
            return category
    return "agent"


def _infer_title(text: str, domain: str, generic_match: dict | None) -> str:
    if generic_match and generic_match.get("name"):
        return f"{generic_match['name']} 真实案例"

    redacted_text = _redact_sensitive_text(text)
    first_line = next((line.strip() for line in redacted_text.splitlines() if line.strip()), "")
    first_line = re.sub(r"\s+", " ", first_line)
    if len(first_line) > 36:
        first_line = first_line[:36].rstrip() + "..."
    domain_label = {
        "vasp": "VASP",
        "slurm": "Slurm",
        "config": "配置",
        "claude": "Claude/API",
        "sync": "同步",
        "tui": "TUI",
        "agent": "Agent",
    }.get(domain, domain)
    return f"{domain_label} 错误: {first_line or '待确认'}"


def _infer_severity(text: str, generic_match: dict | None) -> str:
    lowered = text.lower()
    if generic_match and str(generic_match.get("category", "")).lower() in {"memory", "slurm", "permission", "ssh"}:
        return "error"
    if any(token in lowered for token in ["fatal", "error", "failed", "permission denied", "unauthorized", "out of memory", "oom"]):
        return "error"
    if any(token in lowered for token in ["warning", "warn", "pending"]):
        return "warning"
    return "warning"


def _infer_applies_to(text: str, domain: str) -> list[str]:
    lowered = text.lower()
    if domain == "vasp":
        if "report" in lowered or "analysis" in lowered or "分析" in text:
            return ["vasp_analysis"]
        if "sync" in lowered or "同步" in text:
            return ["vasp_sync", "vasp_analysis"]
        return ["vasp_run", "vasp_analysis"]
    if domain == "slurm":
        return ["slurm_submit", "slurm_monitor", "diagnose_job"]
    if domain == "sync":
        return ["sync", "vasp_sync"]
    if domain == "config":
        return ["startup", "config_check"]
    if domain == "claude":
        return ["llm", "claude_report"]
    if domain == "tui":
        return ["tui"]
    return ["agent"]


def _extract_patterns(text: str) -> list[str]:
    candidates = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _looks_like_error_log(stripped):
            candidates.append(_sanitize_pattern(stripped))
        if len(candidates) >= 4:
            break

    if not candidates:
        candidates.append(_sanitize_pattern(text.strip().splitlines()[0][:100]))

    unique = []
    for item in candidates:
        if item and item not in unique:
            unique.append(item)
    return unique[:4]


def _sanitize_pattern(text: str) -> str:
    pattern = _redact_sensitive_text(text)
    pattern = re.sub(r"\b\d{5,}\b", "JOBID", pattern)
    pattern = re.sub(r"/(?:[A-Za-z0-9_.-]+/){2,}[A-Za-z0-9_.-]+", "/path/to/file", pattern)
    pattern = re.escape(pattern)
    pattern = pattern.replace("\\ ", " ")
    return pattern[:160]


def _redact_sensitive_text(text: str) -> str:
    redacted = str(text)
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|auth[_-]?token|token|password|secret)\s*[:=]\s*['\"]?[^\s'\",;]+",
        lambda match: f"{match.group(1)}=<redacted>",
        redacted,
    )
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "sk-<redacted>", redacted)
    redacted = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<email>", redacted)
    redacted = re.sub(r"/home/[^/\s]+", "/home/<user>", redacted)
    redacted = re.sub(r"(/public\d*/home/)[^/\s]+", r"\1<user>", redacted)
    redacted = re.sub(r"(/public\d*/users?/)[^/\s]+", r"\1<user>", redacted)
    return redacted


def _suggestions_from_match(generic_match: dict | None) -> list[str]:
    if not generic_match:
        return []
    solution = str(generic_match.get("solution", "")).strip()
    if not solution:
        return []
    parts = [part.strip(" ；;。") for part in re.split(r"[；;。]", solution) if part.strip(" ；;。")]
    return parts[:4] or [solution]


def _suggestions_for_domain(domain: str) -> list[str]:
    defaults = {
        "vasp": ["查看远端 stdout/stderr", "确认 VASP 输入和输出文件完整", "必要时同步输出后再分析"],
        "slurm": ["查看 sbatch stderr", "用 squeue/sacct 确认作业状态", "检查 Slurm 参数是否适合当前 partition"],
        "config": ["运行“检查我的超算配置”", "确认 .env 字段和路径正确", "修复后重启 TUI"],
        "claude": ["检查 API Key、Base URL 和模型名", "确认 Claude Code 命令可用", "替换配置后重启 TUI"],
        "sync": ["确认 SSH/SFTP 连接可用", "检查远端目录是否存在", "重新同步并核对文件数"],
        "tui": ["检查终端环境能力", "优先使用鼠标选中文本复制", "安装可用剪贴板后端"],
    }
    return defaults.get(domain, ["保留完整日志", "确认出错阶段", "根据证据逐项排查"])


def _suggest_commands(domain: str, text: str) -> list[str]:
    if domain == "vasp":
        return ["tail -n 80 vasp.out", "tail -n 80 OUTCAR", "ls -lh"]
    if domain == "slurm":
        return ["sacct -j JOBID --format=JobID,State,Elapsed,ExitCode", "squeue -j JOBID"]
    if domain == "config":
        return ["检查我的超算配置", "grep -E '^HPC_|^PARATERA_' .env"]
    if domain == "claude":
        return ["command -v claude", "grep -E '^PARATERA_|^HPC_CLAUDE_CODE_MODEL=' .env"]
    if domain == "sync":
        return ["ssh -i /path/to/private/key -l USER HOST hostname", "ls -lah REMOTE_DIR"]
    if domain == "tui":
        return ["command -v xclip", "command -v wl-copy", "python -c \"import pyperclip\""]
    return ["查看完整日志", "记录出错命令和工作目录"]


def _next_case_id(domain: str, existing_cases: list[dict[str, Any]]) -> str:
    prefix = DOMAIN_PREFIXES.get(domain, "AGENT")
    pattern = re.compile(rf"^{re.escape(prefix)}_REAL_(\d+)$")
    max_id = 0
    for case in existing_cases:
        match = pattern.match(str(case.get("id", "")))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"{prefix}_REAL_{max_id + 1:03d}"
