import json
from datetime import datetime, timezone

from modules.core.paths import JOBS_DIR


REGISTRY_PATH = JOBS_DIR / "job_registry.json"


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
    key = str(job_id)
    now = datetime.now(timezone.utc).isoformat()
    previous = registry.get(key, {})
    registry[key] = {
        **metadata,
        "registered_at": previous.get("registered_at") or metadata.get("registered_at") or now,
        "updated_at": now,
    }
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
