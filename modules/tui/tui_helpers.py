import base64
import os
import re
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

from modules.core.paths import ENV_PATH


load_dotenv(ENV_PATH)


SEARCH_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}


def _local_file_search_roots():
    roots = [Path.cwd()]
    local_workdir = Path(os.getenv("HPC_LOCAL_WORKDIR", "~/hpc-local-jobs")).expanduser()

    if local_workdir not in roots:
        roots.append(local_workdir)

    return roots


def _extract_local_file_candidates(text: str):
    candidates = re.findall(
        r"(?:~|/|\./|\../)?[A-Za-z0-9_./-]+\.(?:py|sh|slurm|sbatch)",
        text,
    )
    cleaned_candidates = []

    for candidate in candidates:
        cleaned = candidate.strip("`'\"，,。；;:：")

        if cleaned not in cleaned_candidates:
            cleaned_candidates.append(cleaned)

    return cleaned_candidates


def _find_files_by_name(file_name: str, root: Path | None = None, limit: int | None = None):
    matches = []
    roots = [root] if root is not None else _local_file_search_roots()

    for search_root in roots:
        search_root = search_root.expanduser()
        if not search_root.exists():
            continue

        root_resolved = search_root.resolve()

        for path in root_resolved.rglob(file_name):
            if not path.is_file():
                continue

            try:
                relative_parts = path.relative_to(root_resolved).parts
            except ValueError:
                relative_parts = path.parts

            if any(part in SEARCH_EXCLUDED_DIRS for part in relative_parts[:-1]):
                continue

            if path not in matches:
                matches.append(path)

            if limit is not None and len(matches) >= limit:
                return matches

    return matches


def _find_unique_file_by_name(file_name: str, root: Path | None = None):
    matches = _find_files_by_name(file_name, root, limit=2)

    return matches[0] if len(matches) == 1 else None


def _has_ambiguous_local_file_candidate(candidate: str):
    if any(separator in candidate for separator in ("/", "\\")):
        return False

    return len(_find_files_by_name(candidate, limit=2)) > 1


def _resolve_local_file_candidate(candidate: str):
    path = Path(candidate).expanduser()

    if path.is_file():
        return path

    for root in _local_file_search_roots():
        rooted_path = (root / candidate).expanduser()

        if rooted_path.is_file():
            return rooted_path

    if any(separator in candidate for separator in ("/", "\\")):
        return None

    return _find_unique_file_by_name(candidate)


def _extract_local_file_paths(text: str):
    paths = []

    for candidate in _extract_local_file_candidates(text):
        path = _resolve_local_file_candidate(candidate)

        if path is not None:
            paths.append(path)

    return paths


def _has_explicit_run_command(text: str):
    return bool(
        re.search(r"\bpython(?:3)?\s+\S+\.py\b", text)
        or re.search(r"\bbash\s+\S+\.sh\b", text)
        or re.search(r"\./[A-Za-z0-9_./-]+", text)
    )


def _requests_no_upload(text: str):
    normalized = text.lower().replace(" ", "")
    return any(
        marker in normalized
        for marker in (
            "不要上传", "别上传", "不用上传", "无需上传",
            "不要传文件", "别传文件", "不要上传文件", "别上传文件",
            "noupload", "donotupload", "don'tupload",
        )
    )


def _uploaded_files_from_paths(paths):
    return [
        {
            "name": path.name,
            "content": path.read_bytes(),
        }
        for path in paths
    ]


def _infer_run_command(uploaded_files):
    for item in uploaded_files:
        name = item["name"]

        if name.endswith(".py"):
            return f"python3 {name}"

    for item in uploaded_files:
        name = item["name"]

        if name.endswith(".sh"):
            return f"bash {name}"

    return None


def _copy_to_clipboard(text: str):
    errors = []

    try:
        import pyperclip

        pyperclip.copy(text)
        return True, ""
    except Exception as error:
        errors.append(f"pyperclip: {type(error).__name__}: {error}")

    powershell = shutil.which("powershell.exe")

    if powershell:
        try:
            encoded_text = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
            command = [
                powershell,
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    f"[Windows.Forms.Clipboard]::SetText([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_text}')))"
                ),
            ]
            subprocess.run(command, check=True, timeout=5)
            return True, ""
        except Exception as error:
            errors.append(f"powershell.exe: {type(error).__name__}: {error}")

    commands = [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],
        ["clip"],
        ["clip.exe"],
    ]

    for command in commands:
        if not shutil.which(command[0]):
            continue

        try:
            subprocess.run(
                command,
                input=text,
                text=True,
                check=True,
                timeout=3,
            )
            return True, ""
        except Exception as error:
            errors.append(f"{command[0]}: {type(error).__name__}: {error}")

    return False, "; ".join(errors) or "没有找到 wl-copy/xclip/xsel/pbcopy/clip.exe 等剪贴板命令"


def _compact_remote_dir(remote_workdir: str):
    if not remote_workdir or remote_workdir == "-":
        return "-"

    return Path(remote_workdir).name or remote_workdir


def _last_nonempty_lines(text: str, limit: int = 5):
    lines = [line for line in text.splitlines() if line.strip()]

    if not lines:
        return ""

    return "\n".join(lines[-limit:])


def _is_vasp_long_workflow_request(text: str):
    normalized = text.lower().replace(" ", "")
    workflow_keywords = [
        "运行并分析",
        "提交并分析",
        "跑完分析",
        "完成后分析",
        "完成后生成报告",
        "自动分析",
        "一键分析",
        "runandanalyze",
        "submitandanalyze",
    ]
    return any(keyword in normalized for keyword in workflow_keywords)
