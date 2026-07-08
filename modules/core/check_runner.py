from __future__ import annotations

import sys

from modules.core.paths import PROJECT_ROOT


def main() -> None:
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    tests_dir = PROJECT_ROOT / "tests"
    if str(tests_dir) not in sys.path:
        sys.path.insert(0, str(tests_dir))

    from tests.run_all_checks import main as run_checks

    run_checks()
