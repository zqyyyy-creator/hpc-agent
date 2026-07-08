import importlib
import os
from pathlib import Path
import sys
import tempfile

from tests import _bootstrap  # noqa: F401


PATH_MODULES = [
    "modules.core.initializer",
    "modules.core.paths",
]


def _reload_initializer(config_dir: Path, data_dir: Path, cache_dir: Path):
    originals = {
        "HPC_AGENT_CONFIG_DIR": os.environ.get("HPC_AGENT_CONFIG_DIR"),
        "HPC_AGENT_DATA_DIR": os.environ.get("HPC_AGENT_DATA_DIR"),
        "HPC_AGENT_CACHE_DIR": os.environ.get("HPC_AGENT_CACHE_DIR"),
    }
    os.environ["HPC_AGENT_CONFIG_DIR"] = str(config_dir)
    os.environ["HPC_AGENT_DATA_DIR"] = str(data_dir)
    os.environ["HPC_AGENT_CACHE_DIR"] = str(cache_dir)

    for module_name in PATH_MODULES:
        sys.modules.pop(module_name, None)

    initializer = importlib.import_module("modules.core.initializer")
    return initializer, originals


def _restore_env(originals: dict[str, str | None]):
    for key, value in originals.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    for module_name in PATH_MODULES:
        sys.modules.pop(module_name, None)


def test_initializer_creates_user_env_from_template():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        initializer, originals = _reload_initializer(
            root / "config",
            root / "data",
            root / "cache",
        )
        try:
            result = initializer.initialize_user_environment()

            assert result["env_created"] is True
            assert result["env_status"] == "created"
            assert result["env_path"] == root / "config" / ".env"
            assert (root / "config" / ".env").is_file()
            assert (root / "data" / "jobs").is_dir()
            assert (root / "data" / "errors").is_dir()
            assert (root / "cache").is_dir()
            assert "PARATERA_API_KEY" in (root / "config" / ".env").read_text(encoding="utf-8")
        finally:
            _restore_env(originals)


def test_initializer_does_not_overwrite_existing_env_by_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config_dir = root / "config"
        config_dir.mkdir(parents=True)
        env_path = config_dir / ".env"
        env_path.write_text("CUSTOM=1\n", encoding="utf-8")
        initializer, originals = _reload_initializer(config_dir, root / "data", root / "cache")
        try:
            result = initializer.initialize_user_environment()

            assert result["env_created"] is False
            assert result["env_status"] == "exists"
            assert env_path.read_text(encoding="utf-8") == "CUSTOM=1\n"
        finally:
            _restore_env(originals)


if __name__ == "__main__":
    test_initializer_creates_user_env_from_template()
    test_initializer_does_not_overwrite_existing_env_by_default()
    print("All initializer checks passed.")
