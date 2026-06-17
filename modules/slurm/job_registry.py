import json
from pathlib import Path


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "jobs" / "job_registry.json"


def _load_registry():
    if not REGISTRY_PATH.exists():
        return {}

    with open(REGISTRY_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_registry(registry):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(REGISTRY_PATH, "w", encoding="utf-8") as file:
        json.dump(registry, file, ensure_ascii=False, indent=2)


def register_job(job_id: str, metadata: dict):
    registry = _load_registry()
    registry[str(job_id)] = metadata
    _save_registry(registry)


def get_job(job_id: str):
    registry = _load_registry()
    return registry.get(str(job_id))


def list_jobs():
    return _load_registry()


def save_jobs(registry: dict):
    _save_registry(registry)


def register_vasp_job(job_id: str, local_job_dir: str, remote_workdir: str):
    register_job(
        job_id,
        {
            "type": "vasp",
            "job_id": str(job_id),
            "local_job_dir": local_job_dir,
            "remote_workdir": remote_workdir,
            "remote_script": f"{remote_workdir}/job.sh",
        },
    )
