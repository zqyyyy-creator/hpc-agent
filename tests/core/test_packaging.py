"""Packaging and console entry point checks."""

import importlib
from pathlib import Path
import tomllib

from tests import _bootstrap
from modules.core.paths import DATA_DIR, ERRORS_DIR, PROJECT_ROOT, resolve_project_path


def test_console_script_points_to_app_main():
    pyproject_path = _bootstrap.PROJECT_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
    assert pyproject["project"]["scripts"]["hpc-agent"] == "app:main"
    assert pyproject["project"]["scripts"]["hpc-agent-check"] == "modules.core.check_runner:main"
    app = importlib.import_module("app")
    assert callable(app.main)
    check_runner = importlib.import_module("modules.core.check_runner")
    assert callable(check_runner.main)


def test_project_paths_are_rooted_and_resolve_relative_paths():
    assert PROJECT_ROOT == _bootstrap.PROJECT_ROOT
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert ERRORS_DIR == PROJECT_ROOT / "data" / "errors"
    assert resolve_project_path("data/errors") == ERRORS_DIR
    assert resolve_project_path(Path("/tmp/hpc-agent-test")) == Path("/tmp/hpc-agent-test")
