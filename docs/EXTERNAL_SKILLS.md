# 外部 Skills 接入指南

本文档说明如何在不修改 HPC Agent 源码的情况下，为 Agent 接入外部只读 Skills。

当前支持两类外部 Skills：

- prompt-only Skill：只有 `SKILL.md`，用于把说明、风格或领域规则注入 RAG 问答。
- external_python Skill：`SKILL.md + handler.py`，用于执行本地只读 Python 工具。

外部 Skills 不会默认写进项目源码目录。推荐用户在自己的目录中维护，例如：

```text
/home/qyz/customize-skills/
├── local-file-summary/
│   ├── SKILL.md
│   └── handler.py
└── quota-check/
    ├── SKILL.md
    └── handler.py
```

## 1. 环境变量

在 `.env` 中配置外部 Skills 目录：

```env
HPC_AGENT_CUSTOM_SKILLS_DIR=/home/qyz/customize-skills
```

如果需要启用外部 Python handler，还需要显式打开全局 trust 开关：

```env
HPC_AGENT_TRUST_EXTERNAL_PYTHON=true
HPC_AGENT_EXTERNAL_PYTHON_TIMEOUT_SECONDS=10
```

安全规则：

- prompt-only Skill 默认可加载。
- external_python Skill 必须同时满足全局 `HPC_AGENT_TRUST_EXTERNAL_PYTHON=true` 和单个 Skill 的 `trusted: true`。
- external_python Skill 必须是 `risk: read_only`。
- external_python Skill 命中后仍然只进入确认流程，用户回复 `确认` 或 `确认执行` 后才会运行。
- external_python handler 会在子进程里运行，并受超时限制。

## 2. 优先级规则

Agent 固定使用以下识别顺序：

1. 系统控制命令：`/help`、`/doctor`、`/config`、`/model`、`/resources`、`/skill`
2. 高风险或确认类内置操作：提交、清理、覆盖、案例写入、归档恢复预览
3. 外部 `external_python + read_only` Skill
4. 内部只读工具
5. 外部 prompt-only Skill + RAG

这样可以避免外部 Skill 抢走提交、清理、覆盖这类关键操作。

## 3. 调试命令

查看已加载和已跳过的 Skills：

```text
/skill list
```

测试单个 Skill，不执行 handler：

```text
/skill test local-file-summary "本地文件统计 /home/qyz/projects/hpc-agent"
```

测试所有 Skills，不执行 handler：

```text
/skill test all "本地文件统计 /home/qyz/projects/hpc-agent"
```

如果要真正执行 external_python Skill，先发送触发语句，再回复确认：

```text
本地文件统计 /home/qyz/projects/hpc-agent
确认
```

## 4. 示例一：local-file-summary

创建目录：

```bash
mkdir -p /home/qyz/customize-skills/local-file-summary
```

写入 `/home/qyz/customize-skills/local-file-summary/SKILL.md`：

```markdown
---
name: local-file-summary
description: 统计本地目录文件数量、总大小和前几个文件名
type: tool
handler: handler.summarize_local_files
triggers: [本地文件统计, 目录统计, 文件统计]
risk: read_only
trusted: true
runtime:
  adapter: external_python
  timeout_seconds: 10
---

只读统计用户指定的本地目录。
```

写入 `/home/qyz/customize-skills/local-file-summary/handler.py`：

```python
from __future__ import annotations

import os
import shlex
from pathlib import Path


MAX_FILES_TO_SCAN = 5000
MAX_NAMES_TO_SHOW = 12


def _extract_directory(question: str) -> Path:
    for token in shlex.split(question):
        if token.startswith(("/", "~", ".")):
            path = Path(token).expanduser()
            if path.is_dir():
                return path.resolve()
    return Path.cwd().resolve()


def summarize_local_files(context: dict) -> dict:
    question = str(context.get("question", ""))
    root = _extract_directory(question)

    file_count = 0
    dir_count = 0
    total_size = 0
    first_names: list[str] = []
    truncated = False

    for current_root, dirs, files in os.walk(root):
        dir_count += len(dirs)
        for filename in files:
            file_count += 1
            path = Path(current_root) / filename
            if len(first_names) < MAX_NAMES_TO_SHOW:
                first_names.append(str(path.relative_to(root)))
            try:
                total_size += path.stat().st_size
            except OSError:
                pass
            if file_count >= MAX_FILES_TO_SCAN:
                truncated = True
                break
        if truncated:
            break

    size_mb = total_size / 1024 / 1024
    names_text = "\n".join(f"- {name}" for name in first_names) if first_names else "- 无文件"
    truncated_note = f"\n\n注意：最多扫描 {MAX_FILES_TO_SCAN} 个文件，当前结果已截断。" if truncated else ""

    return {
        "success": True,
        "message": (
            f"本地文件统计\n\n"
            f"- 目录: {root}\n"
            f"- 文件数: {file_count}\n"
            f"- 子目录数: {dir_count}\n"
            f"- 总大小: {size_mb:.2f} MB\n"
            f"- 前几个文件:\n{names_text}"
            f"{truncated_note}"
        ),
        "data": {
            "path": str(root),
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size_bytes": total_size,
            "truncated": truncated,
            "first_names": first_names,
        },
    }
```

测试：

```text
/skill test local-file-summary "本地文件统计 /home/qyz/projects/hpc-agent"
本地文件统计 /home/qyz/projects/hpc-agent
确认
```

## 5. 示例二：quota-check

创建目录：

```bash
mkdir -p /home/qyz/customize-skills/quota-check
```

写入 `/home/qyz/customize-skills/quota-check/SKILL.md`：

```markdown
---
name: quota-check
description: 只读检查本地工作目录所在磁盘的可用空间
type: tool
handler: handler.check_quota
triggers: [quota, 配额, 磁盘空间, 可用空间]
risk: read_only
trusted: true
runtime:
  adapter: external_python
  timeout_seconds: 10
---

只读检查常用本地工作目录所在文件系统的磁盘空间。
```

写入 `/home/qyz/customize-skills/quota-check/handler.py`：

```python
from __future__ import annotations

import os
import shutil
from pathlib import Path


ENV_DIR_KEYS = [
    "HPC_LOCAL_WORKDIR",
    "HPC_LOCAL_VASP_JOBS_INPUT_DIR",
    "HPC_LOCAL_VASP_JOBS_OUTPUT_DIR",
]


def _format_gb(value: int) -> str:
    return f"{value / 1024 / 1024 / 1024:.2f} GB"


def check_quota(context: dict) -> dict:
    env = context.get("env") or {}
    paths: list[Path] = []

    for key in ENV_DIR_KEYS:
        raw_value = str(env.get(key) or os.getenv(key, "")).strip()
        if raw_value:
            paths.append(Path(raw_value).expanduser())

    if not paths:
        paths.append(Path.home())

    seen: set[str] = set()
    lines = ["本地磁盘空间检查"]
    data = []

    for path in paths:
        existing = path if path.exists() else path.parent
        if not existing.exists():
            lines.append(f"- {path}: 路径不存在，无法检查")
            continue

        resolved = str(existing.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)

        usage = shutil.disk_usage(existing)
        used_percent = usage.used / usage.total * 100 if usage.total else 0
        lines.append(
            f"- {existing}: total={_format_gb(usage.total)}, "
            f"used={_format_gb(usage.used)} ({used_percent:.1f}%), "
            f"free={_format_gb(usage.free)}"
        )
        data.append({
            "path": str(existing),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": used_percent,
        })

    return {
        "success": True,
        "message": "\n".join(lines),
        "data": {"filesystems": data},
    }
```

测试：

```text
/skill test quota-check "帮我查一下 quota"
帮我查一下 quota
确认
```

## 6. 常见问题

如果 `/skill list` 显示 skipped：

- `external_python disabled`：检查 `.env` 是否设置 `HPC_AGENT_TRUST_EXTERNAL_PYTHON=true`。
- `missing trusted: true`：检查该 Skill 的 `SKILL.md` 是否写了 `trusted: true`。
- `handler.py does not exist`：检查 `SKILL.md` 和 `handler.py` 是否在同一个目录。
- `handler.py does not define function`：检查 `handler: handler.xxx` 是否和 `handler.py` 里的函数名一致。

如果触发了 Skill 但没有执行：

- external_python Skill 第一次只会生成确认提示。
- 需要回复 `确认` 或 `确认执行`。
- 如果超时，调小扫描范围或在 `runtime.timeout_seconds` 中增加超时时间。
