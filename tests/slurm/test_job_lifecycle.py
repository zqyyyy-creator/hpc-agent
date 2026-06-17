from pathlib import Path
from tempfile import TemporaryDirectory

from modules.slurm import job_registry
from modules.slurm.job_lifecycle import (
    archive_job_records,
    format_archive_job_records_preview,
    build_archive_job_records_preview,
    build_restore_job_records_preview,
    format_job_detail,
    format_job_record_archives,
    format_job_record_status,
    format_recent_jobs,
    format_vasp_jobs,
    restore_job_records,
)


def _with_temp_registry(callback):
    original_path = job_registry.REGISTRY_PATH
    with TemporaryDirectory() as tmpdir:
        try:
            job_registry.REGISTRY_PATH = Path(tmpdir) / "job_registry.json"
            callback(Path(tmpdir))
        finally:
            job_registry.REGISTRY_PATH = original_path


def test_recent_jobs_lists_latest_local_records():
    def run(tmpdir: Path):
        old_remote = "/remote/hpc-agent-jobs/old"
        job_registry.register_job("10001", {"type": "slurm", "job_id": "10001", "remote_workdir": old_remote})
        job_registry.register_job("20002", {"type": "vasp", "job_id": "20002", "remote_workdir": "/remote/vasp/new"})

        text = format_recent_jobs(limit=2)

        assert "最近 2 个本地记录作业" in text
        assert "20002 | VASP" in text
        assert "10001 | slurm" in text
        assert "查看作业详情 <JobID>" in text

    _with_temp_registry(run)


def test_vasp_jobs_filters_non_vasp_records():
    def run(tmpdir: Path):
        output_dir = tmpdir / "MgO_test"
        raw_dir = output_dir / "raw_output"
        raw_dir.mkdir(parents=True)
        (raw_dir / "OUTCAR").write_text("ok", encoding="utf-8")

        job_registry.register_job("10001", {"type": "slurm", "job_id": "10001"})
        job_registry.register_job(
            "20002",
            {
                "type": "vasp",
                "job_id": "20002",
                "local_output_dir": str(output_dir),
                "local_raw_output_dir": str(raw_dir),
                "remote_workdir": "/remote/vasp/MgO_test",
            },
        )

        text = format_vasp_jobs()

        assert "本地记录的 VASP 作业" in text
        assert "20002 | VASP | MgO_test | 已有本地原始输出" in text
        assert "10001" not in text

    _with_temp_registry(run)


def test_job_detail_reports_paths_and_next_steps():
    def run(tmpdir: Path):
        input_dir = tmpdir / "input" / "NaCl_test"
        analysis_dir = tmpdir / "output" / "NaCl_test" / "analysis"
        input_dir.mkdir(parents=True)
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "summary.md").write_text("# summary", encoding="utf-8")

        job_registry.register_job(
            "30003",
            {
                "type": "vasp",
                "job_id": "30003",
                "local_job_dir": str(input_dir),
                "local_analysis_dir": str(analysis_dir),
                "remote_input_dir": "/remote/input/NaCl_test",
                "remote_output_dir": "/remote/output/NaCl_test",
                "uploaded_files": ["/remote/input/NaCl_test/INCAR"],
            },
        )

        text = format_job_detail("30003")

        assert "Job 30003 详情" in text
        assert "当前本地阶段: 已生成分析报告" in text
        assert "本地输入目录" in text
        assert "远端输入目录: /remote/input/NaCl_test (已记录)" in text
        assert "已生成报告文件: summary.md" in text
        assert "帮我分析 VASP 作业 30003" in text

    _with_temp_registry(run)


def test_job_record_status_summarizes_registry():
    def run(tmpdir: Path):
        raw_dir = tmpdir / "vasp-output" / "raw_output"
        raw_dir.mkdir(parents=True)
        (raw_dir / "OUTCAR").write_text("ok", encoding="utf-8")

        job_registry.register_job("10001", {"type": "slurm", "job_id": "10001"})
        job_registry.register_job(
            "20002",
            {
                "type": "vasp",
                "job_id": "20002",
                "local_raw_output_dir": str(raw_dir),
            },
        )

        text = format_job_record_status()

        assert "本地作业记录状态" in text
        assert "总记录数: 2" in text
        assert "普通 Slurm 作业: 1" in text
        assert "VASP 作业: 1" in text
        assert "已有本地原始输出: 1" in text
        assert "不连接超算" in text

    _with_temp_registry(run)


def test_archive_job_records_preview_keeps_recent_without_writing():
    def run(tmpdir: Path):
        job_registry.register_job("10001", {"type": "slurm", "job_id": "10001", "remote_workdir": "/remote/job/old"})
        job_registry.register_job("20002", {"type": "vasp", "job_id": "20002", "remote_workdir": "/remote/vasp/mid"})
        job_registry.register_job("30003", {"type": "slurm", "job_id": "30003", "remote_workdir": "/remote/job/new"})

        before = job_registry.list_jobs()
        text = format_archive_job_records_preview("预览归档本地作业记录，只保留最近 2 个")
        after = job_registry.list_jobs()

        assert before == after
        assert "本地作业记录归档预览" in text
        assert "只保留最近 2 个" in text
        assert "当前记录数: 3" in text
        assert "将保留: 2" in text
        assert "将归档: 1" in text
        assert "10001 | slurm" in text
        assert "不会删除远端普通作业目录" in text

    _with_temp_registry(run)


def test_archive_job_records_preview_requires_keep_count():
    def run(tmpdir: Path):
        job_registry.register_job("10001", {"type": "slurm", "job_id": "10001"})

        text = format_archive_job_records_preview("预览归档本地作业记录")

        assert "请说明要保留最近多少个" in text

    _with_temp_registry(run)


def test_archive_job_records_moves_records_to_archive_file():
    def run(tmpdir: Path):
        job_registry.register_job("10001", {"type": "slurm", "job_id": "10001"})
        job_registry.register_job("20002", {"type": "vasp", "job_id": "20002"})
        job_registry.register_job("30003", {"type": "slurm", "job_id": "30003"})

        preview = build_archive_job_records_preview("预览归档本地作业记录，只保留最近 2 个")
        result = archive_job_records(preview)

        assert result["success"]
        assert result["archived_count"] == 1
        assert result["remaining_count"] == 2
        assert result["archived_job_ids"] == ["10001"]

        registry = job_registry.list_jobs()
        assert "10001" not in registry
        assert "20002" in registry
        assert "30003" in registry

        archive_path = Path(result["archive_path"])
        assert archive_path.is_file()
        archive_text = archive_path.read_text(encoding="utf-8")
        assert '"10001"' in archive_text
        assert "job_registry_archive_" in archive_path.name

    _with_temp_registry(run)


def test_job_record_archives_lists_archive_files():
    def run(tmpdir: Path):
        archive_dir = tmpdir / "archive"
        archive_dir.mkdir()
        archive_path = archive_dir / "job_registry_archive_20260617_170504.json"
        archive_path.write_text(
            '{"archived_at": "2026-06-17T17:05:04", "records": {"10001": {"type": "slurm"}}}',
            encoding="utf-8",
        )

        text = format_job_record_archives()

        assert "本地作业记录归档文件" in text
        assert "job_registry_archive_20260617_170504.json" in text
        assert "记录数: 1" in text

    _with_temp_registry(run)


def test_restore_job_records_preview_and_restore_missing_records():
    def run(tmpdir: Path):
        job_registry.register_job("30003", {"type": "slurm", "job_id": "30003"})
        archive_dir = tmpdir / "archive"
        archive_dir.mkdir()
        archive_path = archive_dir / "job_registry_archive_20260617_170504.json"
        archive_path.write_text(
            (
                '{"archived_at": "2026-06-17T17:05:04", "records": {'
                '"10001": {"type": "slurm", "job_id": "10001"},'
                '"30003": {"type": "vasp", "job_id": "30003"}'
                '}}'
            ),
            encoding="utf-8",
        )

        preview = build_restore_job_records_preview("预览恢复最近一次本地作业记录归档")

        assert preview["requires_confirmation"]
        assert preview["restore_job_ids"] == ["10001"]
        assert preview["skipped_job_ids"] == ["30003"]
        assert "将恢复: 1" in preview["message"]
        assert "将跳过已存在记录: 1" in preview["message"]

        result = restore_job_records(preview)
        registry = job_registry.list_jobs()

        assert result["success"]
        assert result["restored_count"] == 1
        assert result["skipped_count"] == 0
        assert "10001" in registry
        assert registry["30003"]["type"] == "slurm"

    _with_temp_registry(run)
