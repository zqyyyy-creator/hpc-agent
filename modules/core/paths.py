from __future__ import annotations

import os
from pathlib import Path


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "modules").is_dir()
        and (path / "data").is_dir()
    )


def _find_project_root() -> Path:
    explicit = os.getenv("HPC_AGENT_PROJECT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if _looks_like_project_root(candidate):
            return candidate

    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        if _looks_like_project_root(candidate):
            return candidate

    return module_path.parents[2]


PROJECT_ROOT = _find_project_root()
ENV_PATH = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
ERRORS_DIR = DATA_DIR / "errors"
HPC_DOCUMENTS_DIR = DATA_DIR / "hpc_documents"
JOBS_DIR = DATA_DIR / "jobs"
SKILLS_DIR = PROJECT_ROOT / "skills"
DOCS_DIR = PROJECT_ROOT / "docs"
MODULES_DIR = PROJECT_ROOT / "modules"


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate
