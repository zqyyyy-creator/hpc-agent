from __future__ import annotations

import argparse
import sys

from modules.core.paths import IS_SOURCE_CHECKOUT, PROJECT_ROOT


def _print_section(title: str) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)


def _run_source_checks() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    tests_dir = PROJECT_ROOT / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))

    from tests.run_all_checks import main as run_checks

    run_checks()


def _skip_remote_command(command: str) -> tuple[str, str]:
    return "", "Installed local check skipped remote HPC probing. Use /doctor after configuring .env for live remote checks."


def _run_installed_checks(*, live_hpc: bool = False) -> None:
    from modules.core.project_doctor import format_project_doctor, run_project_doctor

    _print_section("HPC Agent installed package checks")
    print("Running installed-package checks. Source-only tests are not bundled in the wheel.")
    if live_hpc:
        print("--live-hpc is only available from a source checkout; running local installed checks instead.")
    print()

    result = run_project_doctor(run_remote_command=_skip_remote_command)
    print(format_project_doctor(result))

    _print_section("RESULT")
    print("Installed package check completed.")
    print("WARN items usually mean .env or local/HPC paths still need user configuration.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run HPC Agent checks.")
    parser.add_argument(
        "--live-hpc",
        action="store_true",
        help="Also connect to HPC and submit a real Slurm test job when running from a source checkout.",
    )
    args, _unknown = parser.parse_known_args()

    if IS_SOURCE_CHECKOUT and (PROJECT_ROOT / "tests" / "run_all_checks.py").is_file():
        _run_source_checks()
        return

    _run_installed_checks(live_hpc=args.live_hpc)
