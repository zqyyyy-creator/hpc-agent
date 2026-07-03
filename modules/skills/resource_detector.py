from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_PATH = Path("/tmp/hpc-agent/available_resources.json")


def _gb(num_bytes: int | float | None) -> float | None:
    if num_bytes is None:
        return None
    return round(float(num_bytes) / (1024 ** 3), 2)


def _read_linux_memory() -> dict[str, float | None]:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return {"total_gb": None, "available_gb": None, "percent_used": None, "swap_total_gb": None}

    values: dict[str, int] = {}
    for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0]) * 1024

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    percent_used = None
    if total and available is not None:
        percent_used = round((1 - available / total) * 100, 1)

    return {
        "total_gb": _gb(total),
        "available_gb": _gb(available),
        "percent_used": percent_used,
        "swap_total_gb": _gb(values.get("SwapTotal")),
    }


def _run_command(command: list[str], *, timeout: int = 2) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _detect_nvidia_gpus() -> list[dict[str, Any]]:
    if not shutil.which("nvidia-smi"):
        return []

    output = _run_command([
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ])
    gpus = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        memory_total_mb = None
        if parts[1].isdigit():
            memory_total_mb = int(parts[1])
        gpus.append({
            "name": parts[0],
            "memory_total_mb": memory_total_mb,
            "driver_version": parts[2] if len(parts) > 2 else "",
            "backend": "CUDA",
        })
    return gpus


def _detect_amd_gpus() -> list[dict[str, Any]]:
    if not shutil.which("rocm-smi"):
        return []

    output = _run_command(["rocm-smi", "--showproductname"])
    gpus = []
    for line in output.splitlines():
        if "GPU" in line and ":" in line:
            _, name = line.split(":", 1)
            cleaned = name.strip()
            if cleaned:
                gpus.append({"name": cleaned, "backend": "ROCm"})
    return gpus


def _parallel_recommendation(logical_cores: int | None) -> dict[str, Any]:
    cores = logical_cores or 1
    if cores >= 8:
        return {
            "strategy": "high_parallelism",
            "suggested_workers": max(1, cores - 2),
            "libraries": ["joblib", "multiprocessing", "dask"],
        }
    if cores >= 4:
        return {
            "strategy": "moderate_parallelism",
            "suggested_workers": max(1, cores - 1),
            "libraries": ["joblib", "multiprocessing"],
        }
    return {
        "strategy": "sequential_or_low_parallelism",
        "suggested_workers": 1,
        "libraries": ["standard_library"],
    }


def _memory_recommendation(available_gb: float | None) -> dict[str, str]:
    if available_gb is None:
        return {
            "strategy": "unknown_memory",
            "note": "Memory availability could not be detected on this platform.",
        }
    if available_gb < 4:
        return {
            "strategy": "memory_constrained",
            "note": "Prefer streaming, chunking, Dask, Zarr, or HDF5 for large datasets.",
        }
    if available_gb < 16:
        return {
            "strategy": "moderate_memory",
            "note": "Use chunked processing for datasets larger than a few GB.",
        }
    return {
        "strategy": "memory_abundant",
        "note": "Many medium datasets can be loaded in memory, but still avoid unnecessary copies.",
    }


def detect_available_resources(output_path: str | Path = DEFAULT_OUTPUT_PATH) -> dict[str, Any]:
    output_path = Path(output_path)
    logical_cores = os.cpu_count()
    disk_usage = shutil.disk_usage(Path.cwd())
    memory = _read_linux_memory()
    nvidia_gpus = _detect_nvidia_gpus()
    amd_gpus = _detect_amd_gpus()
    available_backends = []
    if nvidia_gpus:
        available_backends.append("CUDA")
    if amd_gpus:
        available_backends.append("ROCm")

    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_skill": "K-Dense-AI/scientific-agent-skills/skills/get-available-resources",
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": sys.version.split()[0],
        },
        "cpu": {
            "logical_cores": logical_cores,
            "architecture": platform.machine(),
            "processor": platform.processor(),
        },
        "memory": memory,
        "disk": {
            "path": str(Path.cwd()),
            "total_gb": _gb(disk_usage.total),
            "available_gb": _gb(disk_usage.free),
            "percent_used": round((disk_usage.used / disk_usage.total) * 100, 1) if disk_usage.total else None,
        },
        "gpu": {
            "nvidia_gpus": nvidia_gpus,
            "amd_gpus": amd_gpus,
            "total_gpus": len(nvidia_gpus) + len(amd_gpus),
            "available_backends": available_backends,
        },
        "recommendations": {
            "parallel_processing": _parallel_recommendation(logical_cores),
            "memory_strategy": _memory_recommendation(memory.get("available_gb")),
            "gpu_acceleration": {
                "available": bool(available_backends),
                "backends": available_backends,
                "note": "Use GPU libraries only when the workload and installed packages support the detected backend.",
            },
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    data["output_path"] = str(output_path)
    return data


def format_available_resources(data: dict[str, Any]) -> str:
    cpu = data["cpu"]
    memory = data["memory"]
    disk = data["disk"]
    gpu = data["gpu"]
    parallel = data["recommendations"]["parallel_processing"]
    memory_strategy = data["recommendations"]["memory_strategy"]
    gpu_backends = ", ".join(gpu["available_backends"]) or "none"

    return "\n".join([
        "本地可用资源检测结果：",
        "",
        f"- CPU: {cpu.get('logical_cores') or 'unknown'} logical cores ({cpu.get('architecture') or 'unknown'})",
        (
            f"- Memory: {memory.get('available_gb')} GB available / {memory.get('total_gb')} GB total"
            if memory.get("total_gb") is not None
            else "- Memory: unknown"
        ),
        f"- Disk: {disk.get('available_gb')} GB available / {disk.get('total_gb')} GB total at {disk.get('path')}",
        f"- GPU: {gpu.get('total_gpus', 0)} detected; backends: {gpu_backends}",
        "",
        "Recommendations:",
        f"- Parallel processing: {parallel['strategy']}, suggested workers: {parallel['suggested_workers']}",
        f"- Memory strategy: {memory_strategy['strategy']} - {memory_strategy['note']}",
        f"- Resource JSON: {data['output_path']}",
    ])


def detect_resources_for_agent(_: str = "") -> str:
    return format_available_resources(detect_available_resources())
