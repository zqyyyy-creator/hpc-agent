import re
import shlex
from pathlib import Path

from modules.core.hpc_config import (
    REMOTE_WORKDIR,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
)
from modules.slurm.remote import run_remote_command
from modules.slurm.remote_utils import safe_remote_dir_name


def is_safe_remote_cleanup_target(path: str) -> bool:
    if not path or path.startswith("/") or path.startswith("-"):
        return False

    parts = Path(path).parts
    return ".." not in parts and "." not in parts


def parse_cleanup_targets(output: str):
    targets = []
    seen = set()

    for line in output.splitlines():
        parts = line.strip().split("\t", 1)

        if len(parts) != 2:
            continue

        kind, path = parts
        path = path.strip().lstrip("./")

        if kind not in {"DIR", "FILE"}:
            continue

        if not is_safe_remote_cleanup_target(path):
            continue

        key = (kind, path)

        if key in seen:
            continue

        seen.add(key)
        targets.append({
            "kind": kind.lower(),
            "path": path,
        })

    return targets


def find_remote_agent_job_cleanup_targets(job_id: str):
    if not re.fullmatch(r"\d{4,}", str(job_id)):
        return {
            "success": False,
            "remote_workdir": REMOTE_WORKDIR,
            "targets": [],
            "output": "",
            "error": "Job ID 格式无效。",
        }

    safe_job_id = shlex.quote(str(job_id))
    command = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        "{ "
        "find . -mindepth 2 -maxdepth 3 -type f "
        f"\\( -name '*_{safe_job_id}.out' -o -name '*_{safe_job_id}.err' \\) "
        "-printf 'DIR\\t%h\\n'; "
        "find . -maxdepth 1 -type f "
        f"\\( -name '*_{safe_job_id}.out' -o -name '*_{safe_job_id}.err' \\) "
        "-printf 'FILE\\t%P\\n'; "
        "} | sort -u"
    )

    output, error = run_remote_command(command)

    return {
        "success": error.strip() == "",
        "remote_workdir": REMOTE_WORKDIR,
        "targets": [
            {**target, "remote_workdir": REMOTE_WORKDIR}
            for target in parse_cleanup_targets(output)
        ],
        "output": output,
        "error": error,
    }


def find_all_remote_agent_cleanup_targets():
    command = (
        f"cd {shlex.quote(REMOTE_WORKDIR)} && "
        "find . -mindepth 1 -maxdepth 1 "
        "-printf '%y\\t%P\\n' | sort"
    )

    output, error = run_remote_command(command)
    targets = []
    seen = set()

    for line in output.splitlines():
        parts = line.strip().split("\t", 1)

        if len(parts) != 2:
            continue

        file_type, path = parts

        if file_type not in {"d", "f"}:
            continue

        if not is_safe_remote_cleanup_target(path):
            continue

        kind = "dir" if file_type == "d" else "file"
        key = (kind, path)

        if key in seen:
            continue

        seen.add(key)
        targets.append({
            "kind": kind,
            "path": path,
            "remote_workdir": REMOTE_WORKDIR,
        })

    return {
        "success": error.strip() == "",
        "remote_workdir": REMOTE_WORKDIR,
        "targets": targets,
        "output": output,
        "error": error,
    }


def vasp_cleanup_roots(scope: str = "both"):
    normalized = (scope or "both").lower()
    roots = []

    if normalized in {"input", "both", "all"} and VASP_REMOTE_INPUT_DIR:
        roots.append(("input", VASP_REMOTE_INPUT_DIR))

    if normalized in {"output", "both", "all"} and VASP_REMOTE_OUTPUT_DIR:
        roots.append(("output", VASP_REMOTE_OUTPUT_DIR))

    return roots


def target_for_remote_vasp_dir(root_dir: str, remote_dir: str, label: str):
    root = root_dir.rstrip("/")
    directory = remote_dir.rstrip("/")

    if directory == root:
        return None

    if not directory.startswith(f"{root}/"):
        return None

    relative_path = directory[len(root) + 1:]

    if not is_safe_remote_cleanup_target(relative_path):
        return None

    return {
        "kind": "dir",
        "path": relative_path,
        "remote_workdir": root_dir,
        "scope": label,
    }


def find_remote_vasp_job_cleanup_targets(selector: str, scope: str = "both"):
    from modules.slurm.job_registry import get_job

    selector = str(selector).strip()
    targets = []
    errors = []
    outputs = []
    roots = vasp_cleanup_roots(scope)

    if not roots:
        return {
            "success": False,
            "remote_workdir": None,
            "remote_workdirs": [],
            "targets": [],
            "output": "",
            "error": "未配置可用的远端 VASP input/output 目录。",
        }

    if re.fullmatch(r"\d{4,}", selector):
        job = get_job(selector) or {}

        if job.get("type") == "vasp":
            registry_paths = {
                "input": job.get("remote_input_dir"),
                "output": job.get("remote_output_dir") or job.get("remote_workdir"),
            }
            for label, root_dir in roots:
                target = target_for_remote_vasp_dir(root_dir, registry_paths.get(label, ""), label)
                if target:
                    targets.append(target)

        safe_selector = shlex.quote(selector)
        for label, root_dir in roots:
            command = (
                f"cd {shlex.quote(root_dir)} && "
                "{ "
                "find . -mindepth 2 -maxdepth 3 -type f "
                f"\\( -name '*_{safe_selector}.out' -o -name '*_{safe_selector}.err' \\) "
                "-printf 'DIR\\t%h\\n'; "
                "find . -maxdepth 1 -type d "
                f"-name '*{safe_selector}*' -printf 'DIR\\t%P\\n'; "
                "} | sort -u"
            )
            output, error = run_remote_command(command)
            outputs.append(f"## {label}\n{output.rstrip()}")
            if error.strip():
                errors.append(f"{label}: {error.rstrip()}")
            for target in parse_cleanup_targets(output):
                targets.append({
                    **target,
                    "remote_workdir": root_dir,
                    "scope": label,
                })
    else:
        safe_name = safe_remote_dir_name(selector)
        if not safe_name:
            return {
                "success": False,
                "remote_workdir": None,
                "remote_workdirs": [root for _, root in roots],
                "targets": [],
                "output": "",
                "error": "VASP 作业名格式无效。",
            }

        for label, root_dir in roots:
            command = (
                f"cd {shlex.quote(root_dir)} && "
                "find . -maxdepth 1 -type d "
                f"\\( -name {shlex.quote(safe_name)} -o -name {shlex.quote(f'*{safe_name}*')} \\) "
                "-printf 'DIR\\t%P\\n' | sort -u"
            )
            output, error = run_remote_command(command)
            outputs.append(f"## {label}\n{output.rstrip()}")
            if error.strip():
                errors.append(f"{label}: {error.rstrip()}")
            for target in parse_cleanup_targets(output):
                targets.append({
                    **target,
                    "remote_workdir": root_dir,
                    "scope": label,
                })

    deduped = []
    seen = set()
    for target in targets:
        key = (target["remote_workdir"], target["kind"], target["path"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)

    return {
        "success": not errors,
        "remote_workdir": None,
        "remote_workdirs": [root for _, root in roots],
        "targets": deduped,
        "output": "\n\n".join(outputs),
        "error": "\n".join(errors),
    }


def find_all_remote_vasp_cleanup_targets(scope: str = "both"):
    roots = vasp_cleanup_roots(scope)
    targets = []
    outputs = []
    errors = []

    if not roots:
        return {
            "success": False,
            "remote_workdir": None,
            "remote_workdirs": [],
            "targets": [],
            "output": "",
            "error": "未配置可用的远端 VASP input/output 目录。",
        }

    for label, root_dir in roots:
        command = (
            f"cd {shlex.quote(root_dir)} && "
            "find . -mindepth 1 -maxdepth 1 -type d "
            "-printf 'DIR\\t%P\\n' | sort"
        )
        output, error = run_remote_command(command)
        outputs.append(f"## {label}\n{output.rstrip()}")
        if error.strip():
            errors.append(f"{label}: {error.rstrip()}")
        for target in parse_cleanup_targets(output):
            targets.append({
                **target,
                "remote_workdir": root_dir,
                "scope": label,
            })

    return {
        "success": not errors,
        "remote_workdir": None,
        "remote_workdirs": [root for _, root in roots],
        "targets": targets,
        "output": "\n\n".join(outputs),
        "error": "\n".join(errors),
    }


def cleanup_remote_agent_targets(targets):
    safe_targets = [
        target
        for target in targets
        if target.get("kind") in {"dir", "file"}
        and is_safe_remote_cleanup_target(target.get("path", ""))
        and target.get("remote_workdir", REMOTE_WORKDIR)
    ]

    if not safe_targets:
        return {
            "success": False,
            "remote_workdir": REMOTE_WORKDIR,
            "remote_workdirs": [],
            "deleted": [],
            "output": "",
            "error": "没有安全的可清理目标。",
        }

    grouped_targets = {}
    for target in safe_targets:
        remote_workdir = target.get("remote_workdir") or REMOTE_WORKDIR
        grouped_targets.setdefault(remote_workdir, []).append(target)

    outputs = []
    errors = []

    for remote_workdir, group in grouped_targets.items():
        quoted_targets = " ".join(
            shlex.quote(target["path"])
            for target in group
        )
        command = (
            f"cd {shlex.quote(remote_workdir)} && "
            f"rm -rf -- {quoted_targets}"
        )

        output, error = run_remote_command(command)
        if output.strip():
            outputs.append(f"{remote_workdir}:\n{output.rstrip()}")
        if error.strip():
            errors.append(f"{remote_workdir}:\n{error.rstrip()}")

    return {
        "success": not errors,
        "remote_workdir": REMOTE_WORKDIR,
        "remote_workdirs": sorted(grouped_targets),
        "deleted": safe_targets,
        "output": "\n\n".join(outputs),
        "error": "\n\n".join(errors),
    }
