"""Packaging and console entry point checks."""

import importlib
import tomllib

from tests import _bootstrap


def test_console_script_points_to_app_main():
    pyproject_path = _bootstrap.PROJECT_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["hpc-agent"] == "app:main"
    app = importlib.import_module("app")
    assert callable(app.main)
