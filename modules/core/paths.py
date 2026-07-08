from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "hpc-agent"


def _expand_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _looks_like_project_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "modules").is_dir()
        and (path / "data").is_dir()
    )


def _find_source_project_root() -> Path | None:
    explicit = os.getenv("HPC_AGENT_PROJECT_ROOT")
    if explicit:
        return _expand_path(explicit)

    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if _looks_like_project_root(candidate):
            return candidate.resolve()

    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        if _looks_like_project_root(candidate):
            return candidate.resolve()

    return None


def _default_user_config_dir() -> Path:
    explicit = os.getenv("HPC_AGENT_CONFIG_DIR")
    if explicit:
        return _expand_path(explicit)

    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return _expand_path(Path(xdg_config_home) / APP_NAME)

    return _expand_path(Path.home() / ".config" / APP_NAME)


def _default_user_data_dir() -> Path:
    explicit = os.getenv("HPC_AGENT_DATA_DIR")
    if explicit:
        return _expand_path(explicit)

    xdg_data_home = os.getenv("XDG_DATA_HOME")
    if xdg_data_home:
        return _expand_path(Path(xdg_data_home) / APP_NAME)

    return _expand_path(Path.home() / ".local" / "share" / APP_NAME)


def _default_user_cache_dir() -> Path:
    explicit = os.getenv("HPC_AGENT_CACHE_DIR")
    if explicit:
        return _expand_path(explicit)

    xdg_cache_home = os.getenv("XDG_CACHE_HOME")
    if xdg_cache_home:
        return _expand_path(Path(xdg_cache_home) / APP_NAME)

    return _expand_path(Path.home() / ".cache" / APP_NAME)


def _find_installed_resource_root() -> Path:
    explicit = os.getenv("HPC_AGENT_RESOURCE_ROOT") or os.getenv("HPC_AGENT_INSTALL_ROOT")
    if explicit:
        return _expand_path(explicit)

    candidates = [
        Path(sys.prefix) / "share" / APP_NAME,
        Path(sys.base_prefix) / "share" / APP_NAME,
        USER_DATA_DIR / "current",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return _expand_path(candidates[0])


def _env_path(project_root: Path, *, source_checkout: bool) -> Path:
    explicit = os.getenv("HPC_AGENT_ENV_PATH")
    if explicit:
        return _expand_path(explicit)

    project_env = project_root / ".env"
    if source_checkout:
        return project_env

    return USER_CONFIG_DIR / ".env"


SOURCE_PROJECT_ROOT = _find_source_project_root()
IS_SOURCE_CHECKOUT = SOURCE_PROJECT_ROOT is not None

USER_CONFIG_DIR = _default_user_config_dir()
USER_DATA_DIR = _default_user_data_dir()
USER_CACHE_DIR = _default_user_cache_dir()

PROJECT_ROOT = SOURCE_PROJECT_ROOT or _find_installed_resource_root()
ENV_PATH = _env_path(PROJECT_ROOT, source_checkout=IS_SOURCE_CHECKOUT)
PROJECT_ENV_PATH = PROJECT_ROOT / ".env"
USER_ENV_PATH = USER_CONFIG_DIR / ".env"

DATA_DIR = PROJECT_ROOT / "data"
ERRORS_DIR = DATA_DIR / "errors"
HPC_DOCUMENTS_DIR = DATA_DIR / "hpc_documents"
SKILLS_DIR = PROJECT_ROOT / "skills"
DOCS_DIR = PROJECT_ROOT / "docs"
MODULES_DIR = Path(__file__).resolve().parents[1]

USER_JOBS_DIR = USER_DATA_DIR / "jobs"
USER_ERRORS_DIR = USER_DATA_DIR / "errors"
JOBS_DIR = Path(os.getenv("HPC_AGENT_JOBS_DIR", DATA_DIR / "jobs" if IS_SOURCE_CHECKOUT else USER_JOBS_DIR)).expanduser()


def resolve_project_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate
