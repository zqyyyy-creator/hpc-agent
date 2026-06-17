import os
import tempfile
from pathlib import Path

from tests import _bootstrap  # noqa: F401

from modules.tui.tui_helpers import (
    _extract_local_file_paths,
    _infer_run_command,
    _requests_no_upload,
)


def test_extract_local_file_paths_finds_unique_bare_filename_recursively():
    original_cwd = Path.cwd()
    original = os.environ.get("HPC_LOCAL_WORKDIR")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        root = Path(tmpdir)
        script = root / "jobs" / "test.py"
        script.parent.mkdir()
        script.write_text("print('ok')\n", encoding="utf-8")
        os.environ["HPC_LOCAL_WORKDIR"] = str(root / "empty-local-workdir")

        os.chdir(root)
        try:
            assert _extract_local_file_paths("帮我运行 test.py") == [script]
        finally:
            os.chdir(original_cwd)
            if original is None:
                os.environ.pop("HPC_LOCAL_WORKDIR", None)
            else:
                os.environ["HPC_LOCAL_WORKDIR"] = original


def test_extract_local_file_paths_ignores_ambiguous_bare_filename():
    original_cwd = Path.cwd()
    original = os.environ.get("HPC_LOCAL_WORKDIR")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        root = Path(tmpdir)
        first = root / "a" / "test.py"
        second = root / "b" / "test.py"
        first.parent.mkdir()
        second.parent.mkdir()
        first.write_text("print('a')\n", encoding="utf-8")
        second.write_text("print('b')\n", encoding="utf-8")
        os.environ["HPC_LOCAL_WORKDIR"] = str(root / "empty-local-workdir")

        os.chdir(root)
        try:
            assert _extract_local_file_paths("帮我运行 test.py") == []
        finally:
            os.chdir(original_cwd)
            if original is None:
                os.environ.pop("HPC_LOCAL_WORKDIR", None)
            else:
                os.environ["HPC_LOCAL_WORKDIR"] = original


def test_extract_local_file_paths_searches_hpc_local_workdir():
    original = os.environ.get("HPC_LOCAL_WORKDIR")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        local_workdir = Path(tmpdir)
        script = local_workdir / "test.py"
        script.write_text("print('ok')\n", encoding="utf-8")
        os.environ["HPC_LOCAL_WORKDIR"] = str(local_workdir)

        try:
            assert _extract_local_file_paths("运行本地的test.py") == [script]
        finally:
            if original is None:
                os.environ.pop("HPC_LOCAL_WORKDIR", None)
            else:
                os.environ["HPC_LOCAL_WORKDIR"] = original


def test_requests_no_upload_detects_negated_uploads():
    assert _requests_no_upload("运行 python train.py，不要上传文件")
    assert _requests_no_upload("运行 python train.py，别上传")
    assert not _requests_no_upload("上传 train.py 并运行")


def test_infer_run_command_uses_python3_for_python_files():
    assert _infer_run_command([{"name": "test.py", "content": b""}]) == "python3 test.py"
