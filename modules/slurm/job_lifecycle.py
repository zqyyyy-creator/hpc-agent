from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.slurm import job_registry
from modules.slurm.job_registry import get_job, list_jobs, save_jobs
from modules.slurm.job_query import resolve_job_id_for_text


LOCAL_PATH_FIELDS = (
    "local_job_dir",
    "local_output_dir",
    "local_raw_output_dir",
    "local_analysis_dir",
)


def _is_vasp_job(job: dict[str, Any]) -> bool:
    kind = str(job.get("type") or job.get("kind") or "").lower()
    return kind == "vasp"


def _job_kind(job: dict[str, Any]) -> str:
    if _is_vasp_job(job):
        return "VASP"
    return str(job.get("type") or job.get("kind") or "Slurm")


def _path_exists(path: str | None) -> bool:
    return bool(path) and Path(path).exists()


def _dir_has_files(path: str | None) -> bool:
    if not path:
        return False
    directory = Path(path)
    return directory.is_dir() and any(directory.iterdir())


def _analysis_markdown_files(path: str | None) -> list[Path]:
    if not path:
        return []
    directory = Path(path)
    if not directory.is_dir():
        return []
    return sorted(item for item in directory.glob("*.md") if item.name != "report_context.md")


def _mtime_for_path(path: str | None) -> float:
    if not path:
        return 0.0
    candidate = Path(path)
    try:
        return candidate.stat().st_mtime
    except OSError:
        return 0.0


def _numeric_job_id(job_id: str) -> int:
    return int(job_id) if str(job_id).isdigit() else 0


def _job_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[float, int]:
    job_id, job = item
    mtimes = [_mtime_for_path(str(job.get(field) or "")) for field in LOCAL_PATH_FIELDS]
    return (max(mtimes, default=0.0), _numeric_job_id(job_id))


def _job_name(job: dict[str, Any]) -> str:
    for field in ("local_job_dir", "local_output_dir", "remote_workdir", "remote_output_dir"):
        value = job.get(field)
        if value:
            return Path(str(value).rstrip("/")).name
    return "-"


def _job_stage(job: dict[str, Any]) -> str:
    if _analysis_markdown_files(job.get("local_analysis_dir")):
        return "已生成分析报告"
    if _path_exists(job.get("report_context")) or _path_exists(job.get("file_manifest")):
        return "已建立分析上下文"
    if _dir_has_files(job.get("local_raw_output_dir")):
        return "已有本地原始输出"
    if _dir_has_files(job.get("local_output_dir")):
        return "已有本地输出目录"
    if job.get("remote_workdir") or job.get("remote_output_dir"):
        return "已登记远端目录"
    return "仅本地登记"


def _format_size(num_bytes: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def _iter_jobs(kind: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    jobs = list_jobs()
    items = [(str(job_id), dict(job or {})) for job_id, job in jobs.items()]
    if kind == "vasp":
        items = [(job_id, job) for job_id, job in items if _is_vasp_job(job)]
    return sorted(items, key=_job_sort_key, reverse=True)


def _format_job_row(job_id: str, job: dict[str, Any]) -> str:
    return f"- {job_id} | {_job_kind(job)} | {_job_name(job)} | {_job_stage(job)}"


def format_job_record_status() -> str:
    registry = list_jobs()
    items = _iter_jobs()
    total = len(items)
    vasp_count = sum(1 for _, job in items if _is_vasp_job(job))
    slurm_count = total - vasp_count
    registry_path = job_registry.REGISTRY_PATH
    file_size = registry_path.stat().st_size if registry_path.exists() else 0

    if not registry:
        return (
            "本地作业记录状态\n"
            f"- 记录文件: {registry_path}\n"
            "- 总记录数: 0\n"
            "- 文件大小: 0 B\n\n"
            "当前还没有本地作业记录。"
        )

    numeric_ids = [_numeric_job_id(job_id) for job_id, _ in items if _numeric_job_id(job_id)]
    stage_counts: dict[str, int] = {}
    for _, job in items:
        stage = _job_stage(job)
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    lines = [
        "本地作业记录状态",
        f"- 记录文件: {registry_path}",
        f"- 文件大小: {_format_size(file_size)}",
        f"- 总记录数: {total}",
        f"- 普通 Slurm 作业: {slurm_count}",
        f"- VASP 作业: {vasp_count}",
    ]

    if numeric_ids:
        lines.extend([
            f"- 最早 Job ID: {min(numeric_ids)}",
            f"- 最新 Job ID: {max(numeric_ids)}",
        ])

    lines.append("")
    lines.append("本地阶段分布:")
    for stage, count in sorted(stage_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {stage}: {count}")

    lines.extend([
        "",
        "说明: 这里只统计本地 job_registry.json，不连接超算，也不会检查远端文件是否仍存在。",
        "可继续说：预览归档本地作业记录，只保留最近 100 个。",
    ])
    return "\n".join(lines)


def _extract_keep_count(text: str) -> int | None:
    match = re.search(r"(?:保留|最近|前)\s*(\d+)\s*(?:个|条|项)?", text)
    if match:
        return int(match.group(1))

    match = re.search(r"keep\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def build_archive_job_records_preview(text: str, preview_limit: int = 10) -> dict[str, Any]:
    keep_count = _extract_keep_count(text)
    if keep_count is None:
        return {
            "success": False,
            "message": (
                "请说明要保留最近多少个本地作业记录。\n"
                "例如：预览归档本地作业记录，只保留最近 100 个"
            ),
            "requires_confirmation": False,
        }

    if keep_count <= 0:
        return {
            "success": False,
            "message": "保留数量必须大于 0。请改成类似：只保留最近 100 个。",
            "requires_confirmation": False,
        }

    items = _iter_jobs()
    total = len(items)
    keep_items = items[:keep_count]
    archive_items = items[keep_count:]

    lines = [
        "本地作业记录归档预览",
        f"- 策略: 只保留最近 {keep_count} 个",
        f"- 当前记录数: {total}",
        f"- 将保留: {len(keep_items)}",
        f"- 将归档: {len(archive_items)}",
        "",
        "安全说明:",
        "- 这是预览，不会修改任何文件。",
        "- 归档目标仅是 data/jobs/job_registry.json 里的记录。",
        "- 不会删除本地 VASP 输入目录。",
        "- 不会删除本地 VASP 输出目录。",
        "- 不会删除远端普通作业目录或远端 VASP input/output 目录。",
    ]

    if not archive_items:
        lines.extend([
            "",
            "当前记录数没有超过保留数量，不需要归档。",
        ])
        return {
            "success": True,
            "message": "\n".join(lines),
            "requires_confirmation": False,
            "keep_count": keep_count,
            "archive_job_ids": [],
        }

    lines.extend([
        "",
        f"即将归档的记录预览（最多显示 {preview_limit} 个）:",
    ])
    lines.extend(_format_job_row(job_id, job) for job_id, job in archive_items[:preview_limit])

    if len(archive_items) > preview_limit:
        lines.append(f"- ... 还有 {len(archive_items) - preview_limit} 条未显示")

    lines.extend([
        "",
        "如要执行，请回复：确认归档本地作业记录",
        "如要放弃，请回复：取消",
    ])
    archive_job_ids = [job_id for job_id, _ in archive_items]
    keep_job_ids = [job_id for job_id, _ in keep_items]
    return {
        "success": True,
        "message": "\n".join(lines),
        "requires_confirmation": True,
        "keep_count": keep_count,
        "total": total,
        "keep_job_ids": keep_job_ids,
        "archive_job_ids": archive_job_ids,
    }


def format_archive_job_records_preview(text: str, preview_limit: int = 10) -> str:
    return build_archive_job_records_preview(text, preview_limit=preview_limit)["message"]


def archive_job_records(payload: dict[str, Any]) -> dict[str, Any]:
    archive_job_ids = [str(job_id) for job_id in payload.get("archive_job_ids") or []]
    keep_count = payload.get("keep_count")

    if not archive_job_ids:
        return {
            "success": False,
            "message": "没有可归档的本地作业记录。请先执行归档预览。",
        }

    registry = list_jobs()
    records_to_archive = {
        job_id: registry[job_id]
        for job_id in archive_job_ids
        if job_id in registry
    }

    if not records_to_archive:
        return {
            "success": False,
            "message": "预览中的作业记录已经不在当前 job_registry.json 中，未执行归档。",
        }

    archive_dir = job_registry.REGISTRY_PATH.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = archive_dir / f"job_registry_archive_{timestamp}.json"
    archive_payload = {
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": f"keep_recent_{keep_count}" if keep_count else "selected_job_ids",
        "archived_job_ids": list(records_to_archive.keys()),
        "records": records_to_archive,
    }

    with open(archive_path, "w", encoding="utf-8") as file:
        json.dump(archive_payload, file, ensure_ascii=False, indent=2)

    remaining = {
        job_id: job
        for job_id, job in registry.items()
        if job_id not in records_to_archive
    }
    save_jobs(remaining)

    lines = [
        "本地作业记录归档完成",
        f"- 归档记录数: {len(records_to_archive)}",
        f"- 当前保留记录数: {len(remaining)}",
        f"- 归档文件: {archive_path}",
        "",
        "安全说明: 只移动了 job_registry.json 里的记录，没有删除任何本地作业文件或远端目录。",
    ]
    return {
        "success": True,
        "message": "\n".join(lines),
        "archive_path": str(archive_path),
        "archived_count": len(records_to_archive),
        "remaining_count": len(remaining),
        "archived_job_ids": list(records_to_archive.keys()),
    }


def _archive_dir() -> Path:
    return job_registry.REGISTRY_PATH.parent / "archive"


def _archive_files() -> list[Path]:
    directory = _archive_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob("job_registry_archive_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def _archive_path_from_text(text: str) -> Path | None:
    match = re.search(r"(job_registry_archive_\d{8}_\d{6}\.json)", text)
    if match:
        return _archive_dir() / match.group(1)
    return None


def _load_archive(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def format_job_record_archives(limit: int = 10) -> str:
    files = _archive_files()
    if not files:
        return "当前没有找到本地作业记录归档文件。"

    lines = [f"本地作业记录归档文件（最近 {min(limit, len(files))} 个）:"]
    for path in files[:limit]:
        try:
            archive = _load_archive(path)
            count = len(archive.get("records") or {})
            archived_at = archive.get("archived_at", "-")
        except (OSError, json.JSONDecodeError):
            count = "读取失败"
            archived_at = "-"
        lines.append(f"- {path.name} | 记录数: {count} | 归档时间: {archived_at}")

    lines.extend([
        "",
        "可继续说：预览恢复最近一次本地作业记录归档",
        "或：预览恢复归档文件 job_registry_archive_YYYYMMDD_HHMMSS.json",
    ])
    return "\n".join(lines)


def build_restore_job_records_preview(text: str, preview_limit: int = 10) -> dict[str, Any]:
    archive_path = _archive_path_from_text(text)
    if archive_path is None:
        files = _archive_files()
        archive_path = files[0] if files else None

    if archive_path is None:
        return {
            "success": False,
            "message": "当前没有找到可恢复的本地作业记录归档文件。",
            "requires_confirmation": False,
        }

    if not archive_path.exists():
        return {
            "success": False,
            "message": f"没有找到归档文件: {archive_path.name}",
            "requires_confirmation": False,
        }

    try:
        archive = _load_archive(archive_path)
    except (OSError, json.JSONDecodeError) as error:
        return {
            "success": False,
            "message": f"读取归档文件失败: {type(error).__name__}: {error}",
            "requires_confirmation": False,
        }

    records = archive.get("records") or {}
    if not isinstance(records, dict) or not records:
        return {
            "success": False,
            "message": f"归档文件 {archive_path.name} 里没有可恢复的 records。",
            "requires_confirmation": False,
        }

    registry = list_jobs()
    restore_job_ids = [str(job_id) for job_id in records if str(job_id) not in registry]
    skipped_job_ids = [str(job_id) for job_id in records if str(job_id) in registry]

    lines = [
        "本地作业记录恢复预览",
        f"- 归档文件: {archive_path}",
        f"- 归档内记录数: {len(records)}",
        f"- 将恢复: {len(restore_job_ids)}",
        f"- 将跳过已存在记录: {len(skipped_job_ids)}",
        "",
        "安全说明:",
        "- 这是预览，不会修改任何文件。",
        "- 恢复只会把归档中的记录合并回 job_registry.json。",
        "- 默认不覆盖当前已经存在的同 Job ID 记录。",
        "- 不会创建、删除或修改任何本地/远端作业目录。",
    ]

    if restore_job_ids:
        lines.extend(["", f"将恢复的记录预览（最多显示 {preview_limit} 个）:"])
        for job_id in restore_job_ids[:preview_limit]:
            lines.append(_format_job_row(job_id, records[job_id]))
        if len(restore_job_ids) > preview_limit:
            lines.append(f"- ... 还有 {len(restore_job_ids) - preview_limit} 条未显示")

    if skipped_job_ids:
        lines.extend(["", f"将跳过的已存在 Job ID（最多显示 {preview_limit} 个）:"])
        for job_id in skipped_job_ids[:preview_limit]:
            lines.append(f"- {job_id}")
        if len(skipped_job_ids) > preview_limit:
            lines.append(f"- ... 还有 {len(skipped_job_ids) - preview_limit} 条未显示")

    if not restore_job_ids:
        lines.extend(["", "当前 registry 已包含该归档里的全部 Job ID，不需要恢复。"])
        return {
            "success": True,
            "message": "\n".join(lines),
            "requires_confirmation": False,
            "archive_path": str(archive_path),
            "restore_job_ids": [],
            "skipped_job_ids": skipped_job_ids,
        }

    lines.extend([
        "",
        "如要执行，请回复：确认恢复本地作业记录归档",
        "如要放弃，请回复：取消",
    ])
    return {
        "success": True,
        "message": "\n".join(lines),
        "requires_confirmation": True,
        "archive_path": str(archive_path),
        "restore_job_ids": restore_job_ids,
        "skipped_job_ids": skipped_job_ids,
    }


def restore_job_records(payload: dict[str, Any]) -> dict[str, Any]:
    archive_path = Path(str(payload.get("archive_path") or ""))
    restore_job_ids = [str(job_id) for job_id in payload.get("restore_job_ids") or []]

    if not archive_path.exists() or not restore_job_ids:
        return {
            "success": False,
            "message": "没有可恢复的本地作业记录。请先执行恢复预览。",
        }

    try:
        archive = _load_archive(archive_path)
    except (OSError, json.JSONDecodeError) as error:
        return {
            "success": False,
            "message": f"读取归档文件失败: {type(error).__name__}: {error}",
        }

    records = archive.get("records") or {}
    registry = list_jobs()
    restored: dict[str, Any] = {}
    skipped_existing: list[str] = []
    missing_in_archive: list[str] = []

    for job_id in restore_job_ids:
        if job_id in registry:
            skipped_existing.append(job_id)
        elif job_id in records:
            registry[job_id] = records[job_id]
            restored[job_id] = records[job_id]
        else:
            missing_in_archive.append(job_id)

    if restored:
        save_jobs(registry)

    lines = [
        "本地作业记录恢复完成",
        f"- 恢复记录数: {len(restored)}",
        f"- 跳过已存在记录: {len(skipped_existing)}",
        f"- 归档中缺失记录: {len(missing_in_archive)}",
        f"- 当前总记录数: {len(registry)}",
        f"- 来源归档: {archive_path}",
        "",
        "安全说明: 只合并了 job_registry.json 里的记录，没有修改任何本地作业文件或远端目录。",
    ]
    return {
        "success": True,
        "message": "\n".join(lines),
        "archive_path": str(archive_path),
        "restored_count": len(restored),
        "skipped_count": len(skipped_existing),
        "missing_count": len(missing_in_archive),
        "restored_job_ids": list(restored.keys()),
    }


def format_recent_jobs(limit: int = 10) -> str:
    items = _iter_jobs()[:limit]
    if not items:
        return "本地 job_registry.json 里还没有记录作业。"

    lines = [
        f"最近 {len(items)} 个本地记录作业:",
        *(_format_job_row(job_id, job) for job_id, job in items),
        "",
        "可继续说：查看作业详情 <JobID> / 诊断作业 <JobID> / 查看 <JobID> 的状态。",
    ]
    return "\n".join(lines)


def format_vasp_jobs(limit: int = 20) -> str:
    items = _iter_jobs(kind="vasp")[:limit]
    if not items:
        return "本地 job_registry.json 里还没有 VASP 作业记录。"

    lines = [
        f"本地记录的 VASP 作业（最多 {limit} 个）:",
        *(_format_job_row(job_id, job) for job_id, job in items),
        "",
        "可继续说：查看作业详情 <JobID> / 同步 VASP 作业 <JobID> 输出 / 帮我分析 VASP 作业 <JobID>。",
    ]
    return "\n".join(lines)


def _format_path_line(label: str, value: str | None) -> str | None:
    if not value:
        return None
    if label.startswith("远端"):
        marker = "已记录"
    else:
        marker = "存在" if _path_exists(value) else "未发现本地路径" if value.startswith("/") else "已记录"
    return f"- {label}: {value} ({marker})"


def _format_uploaded_files(job: dict[str, Any]) -> list[str]:
    files = job.get("uploaded_files") or []
    if not files:
        return []
    preview = [f"- 已上传文件: {len(files)} 个"]
    for item in files[:5]:
        preview.append(f"  - {item}")
    if len(files) > 5:
        preview.append(f"  - ... 还有 {len(files) - 5} 个")
    return preview


def _format_next_steps(job_id: str, job: dict[str, Any]) -> list[str]:
    steps = [
        f"- 查看状态：查看 {job_id} 的状态",
        f"- 查看输出：读取 {job_id} 的输出",
        f"- 失败诊断：诊断作业 {job_id}",
    ]
    if _is_vasp_job(job):
        if not _dir_has_files(job.get("local_raw_output_dir")):
            steps.append(f"- 拉回结果：同步 VASP 作业 {job_id} 输出")
        steps.append(f"- 生成报告：帮我分析 VASP 作业 {job_id}")
    return steps


def format_job_detail(job_id: str) -> str:
    job = get_job(str(job_id))
    if not job:
        return (
            f"没有在本地 job_registry.json 中找到 Job {job_id}。\n"
            "可以先说“查看最近作业”，确认这个作业是否被 Agent 记录过。"
        )

    report_files = _analysis_markdown_files(job.get("local_analysis_dir"))
    lines = [
        f"Job {job_id} 详情",
        f"- 类型: {_job_kind(job)}",
        f"- 作业名/目录名: {_job_name(job)}",
        f"- 当前本地阶段: {_job_stage(job)}",
    ]

    path_lines = [
        _format_path_line("本地输入目录", job.get("local_job_dir")),
        _format_path_line("本地输出目录", job.get("local_output_dir")),
        _format_path_line("本地 raw_output", job.get("local_raw_output_dir")),
        _format_path_line("本地 analysis", job.get("local_analysis_dir")),
        _format_path_line("远端工作目录", job.get("remote_workdir")),
        _format_path_line("远端输入目录", job.get("remote_input_dir")),
        _format_path_line("远端输出目录", job.get("remote_output_dir")),
        _format_path_line("远端脚本", job.get("remote_script")),
    ]
    lines.extend(item for item in path_lines if item)

    if job.get("file_manifest"):
        lines.append(f"- 文件清单: {job['file_manifest']}")
    if job.get("report_context"):
        lines.append(f"- 报告上下文: {job['report_context']}")
    if report_files:
        lines.append("- 已生成报告文件: " + ", ".join(path.name for path in report_files))

    lines.extend(_format_uploaded_files(job))
    lines.append("")
    lines.append("建议下一步:")
    lines.extend(_format_next_steps(str(job_id), job))
    return "\n".join(lines)


def format_job_detail_for_request(text: str, *, state=None) -> str:
    job_id = resolve_job_id_for_text(text, state=state)
    if not job_id:
        match = re.search(r"(?<!\d)(\d{4,})(?!\d)", text)
        job_id = match.group(1) if match else None
    if not job_id:
        return "你想查看哪个作业的详情？请提供 Job ID，或先说“查看最近作业”。"
    return format_job_detail(job_id)
