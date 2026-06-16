import base64
import re
import shutil
import subprocess
from pathlib import Path


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


def _extract_local_file_paths(text: str):
    paths = []

    for candidate in _extract_local_file_candidates(text):
        path = Path(candidate).expanduser()

        if path.is_file():
            paths.append(path)

    return paths


def _has_explicit_run_command(text: str):
    return bool(
        re.search(r"\bpython(?:3)?\s+\S+\.py\b", text)
        or re.search(r"\bbash\s+\S+\.sh\b", text)
        or re.search(r"\./[A-Za-z0-9_./-]+", text)
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
            return f"python {name}"

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
