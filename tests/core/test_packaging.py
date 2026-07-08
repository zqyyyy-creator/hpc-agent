"""Packaging and console entry point checks."""

import importlib
import json
from pathlib import Path
import tomllib

from tests import _bootstrap
from modules.core.paths import (
    APP_NAME,
    DATA_DIR,
    ENV_PATH,
    ERRORS_DIR,
    IS_SOURCE_CHECKOUT,
    JOBS_DIR,
    MODULES_DIR,
    PROJECT_ENV_PATH,
    PROJECT_ROOT,
    USER_CONFIG_DIR,
    USER_DATA_DIR,
    USER_ENV_PATH,
    USER_JOBS_DIR,
    resolve_project_path,
)


def test_console_script_points_to_app_main():
    pyproject_path = _bootstrap.PROJECT_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["build-system"]["build-backend"] == "setuptools.build_meta"
    assert pyproject["project"]["scripts"]["hpc-agent"] == "app:main"
    assert pyproject["project"]["scripts"]["hpc-agent-check"] == "modules.core.check_runner:main"
    assert pyproject["project"]["scripts"]["hpc-agent-init"] == "modules.core.initializer:main"
    app = importlib.import_module("app")
    assert callable(app.main)
    check_runner = importlib.import_module("modules.core.check_runner")
    assert callable(check_runner.main)
    assert callable(check_runner._run_installed_checks)
    initializer = importlib.import_module("modules.core.initializer")
    assert callable(initializer.main)


def test_project_paths_are_rooted_and_resolve_relative_paths():
    assert PROJECT_ROOT == _bootstrap.PROJECT_ROOT
    assert IS_SOURCE_CHECKOUT is True
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert ERRORS_DIR == PROJECT_ROOT / "data" / "errors"
    assert JOBS_DIR == PROJECT_ROOT / "data" / "jobs"
    assert PROJECT_ROOT in MODULES_DIR.parents
    assert resolve_project_path("data/errors") == ERRORS_DIR
    assert resolve_project_path(Path("/tmp/hpc-agent-test")) == Path("/tmp/hpc-agent-test")


def test_user_paths_are_available_without_changing_source_checkout_defaults():
    assert APP_NAME == "hpc-agent"
    assert ENV_PATH == PROJECT_ENV_PATH
    assert USER_ENV_PATH == USER_CONFIG_DIR / ".env"
    assert USER_JOBS_DIR == USER_DATA_DIR / "jobs"


def test_wheel_data_files_include_read_only_resources_only():
    pyproject_path = _bootstrap.PROJECT_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    data_files = pyproject["tool"]["setuptools"]["data-files"]
    packaged_files = {
        path
        for paths in data_files.values()
        for path in paths
    }

    expected_files = {
        ".env.example",
        "data/errors/README.md",
        "data/errors/generic_errors.json",
        "data/errors/real_cases.json",
        *[
            str(path.relative_to(_bootstrap.PROJECT_ROOT))
            for path in (_bootstrap.PROJECT_ROOT / "data" / "hpc_documents").glob("*.txt")
        ],
        *[
            str(path.relative_to(_bootstrap.PROJECT_ROOT))
            for path in (_bootstrap.PROJECT_ROOT / "docs").glob("*.md")
        ],
        *[
            str(path.relative_to(_bootstrap.PROJECT_ROOT))
            for path in (_bootstrap.PROJECT_ROOT / "skills").glob("*/SKILL.md")
        ],
    }

    assert expected_files <= packaged_files
    assert not any(path.startswith("data/jobs/") for path in packaged_files)


def test_install_script_supports_wheel_install_and_command_links():
    script_path = _bootstrap.PROJECT_ROOT / "scripts" / "install.sh"
    script = script_path.read_text(encoding="utf-8")

    assert script_path.is_file()
    assert "set -eu" in script
    assert "HPC_AGENT_WHEEL" in script
    assert "HPC_AGENT_PACKAGE" in script
    assert "HPC_AGENT_PIP_INDEX_URL" in script
    assert "HPC_AGENT_FORCE_REINSTALL" in script
    assert "HPC_AGENT_PIP_NO_DEPS" in script
    assert "--force-reinstall" in script
    assert "--no-deps" in script
    assert "hpc-agent-init" in script
    assert "hpc-agent-check" in script
    assert "hpc-agent" in script


def test_private_server_release_templates_are_present():
    packaging_dir = _bootstrap.PROJECT_ROOT / "packaging"
    latest_template = packaging_dir / "latest.example.json"

    assert (packaging_dir / "PRIVATE_SERVER_LAYOUT.md").is_file()
    assert (packaging_dir / "RELEASE_NOTES_TEMPLATE.md").is_file()
    assert latest_template.is_file()

    latest = json.loads(latest_template.read_text(encoding="utf-8"))
    assert latest["name"] == "hpc-agent"
    assert latest["version"]
    assert latest["python"] == ">=3.12"
    assert latest["files"]["wheel"]["path"].endswith(".whl")
    assert latest["files"]["wheel"]["sha256"]
    assert latest["files"]["install_script"]["path"].endswith("install.sh")
    assert latest["commands"]["install"].startswith("HPC_AGENT_WHEEL=")
