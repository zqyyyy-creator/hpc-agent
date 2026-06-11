import _bootstrap  # noqa: F401
from tempfile import TemporaryDirectory

from modules.job_submitter import (
    VASP_LOCAL_JOBS_DIR,
    VASP_REMOTE_INPUT_DIR,
    VASP_REMOTE_OUTPUT_DIR,
    VASP_PARTITION,
    extract_source_dir_from_text,
    prepare_vasp_submit_script,
    register_existing_vasp_job_from_text,
    resolve_vasp_job_input_dir,
    submit_prepared_vasp_script,
    validate_vasp_input_files,
)
from modules.router import detect_intent
from modules.slurm_tools import _add_vasp_input_sync
from modules.vasp_assistant import generate_vasp_sbatch_script


DEFAULT_VASP_SETUP = (
    "source /public1/soft/intel/2020u4/compilers_and_libraries_2020.4.304/"
    "linux/bin/compilervars.sh intel64"
)
DEFAULT_VASP_RUN = "mpirun /public1/soft/vasp > vasp.out"


def assert_contains(text: str, expected: str):
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in:\n{text}")


def assert_not_contains(text: str, unexpected: str):
    if unexpected in text:
        raise AssertionError(f"Did not expect to find {unexpected!r} in:\n{text}")


def test_generate_vasp_script_defaults():
    request = "帮我生成一个 VASP 结构优化脚本"
    script = generate_vasp_sbatch_script(request)

    assert detect_intent(request) == "generate_vasp_job"
    assert_contains(script, "#SBATCH --job-name=vasp_relax")
    assert_contains(script, "#SBATCH --nodes=1")
    assert_contains(script, "#SBATCH --ntasks-per-node=32")
    assert_contains(script, "#SBATCH --time=24:00:00")
    assert_contains(script, "test -f INCAR")
    assert_contains(script, "test -f POSCAR")
    assert_contains(script, "test -f POTCAR")
    assert_contains(script, "test -f KPOINTS")
    assert_contains(script, DEFAULT_VASP_SETUP)
    assert_contains(script, DEFAULT_VASP_RUN)


def test_generate_vasp_script_extracts_resources():
    request = "帮我生成 VASP 脚本，2 个节点，每节点 64 核，运行 48 小时，命令是 mpirun /public1/soft/vasp"
    script = generate_vasp_sbatch_script(request)

    assert detect_intent(request) == "generate_vasp_job"
    assert_contains(script, "#SBATCH --nodes=2")
    assert_contains(script, "#SBATCH --ntasks-per-node=64")
    assert_contains(script, "#SBATCH --time=48:00:00")
    assert_contains(script, DEFAULT_VASP_RUN)


def test_submit_vasp_job_preview_handles_partition():
    request = "帮我提交一个 VASP 结构优化任务，1 个节点 32 核，运行 24 小时"
    prepared = prepare_vasp_submit_script(request)

    if not prepared["ready"]:
        raise AssertionError(f"VASP submit script should be ready: {prepared['message']}")

    assert detect_intent(request) == "submit_vasp_job"
    if VASP_PARTITION:
        assert_contains(prepared["script"], f"#SBATCH --partition={VASP_PARTITION}")
    else:
        assert_not_contains(prepared["script"], "#SBATCH --partition")
    assert_contains(prepared["script"], "#SBATCH --nodes=1")
    assert_contains(prepared["script"], "#SBATCH --ntasks-per-node=32")
    assert_contains(prepared["script"], DEFAULT_VASP_SETUP)
    assert_contains(prepared["script"], DEFAULT_VASP_RUN)
    if prepared["local_jobs_dir"] != str(_bootstrap.Path(VASP_LOCAL_JOBS_DIR).resolve()):
        raise AssertionError(f"Unexpected VASP local jobs dir: {prepared['local_jobs_dir']}")
    if prepared["remote_input_dir"] != VASP_REMOTE_INPUT_DIR:
        raise AssertionError(f"Unexpected VASP remote input dir: {prepared['remote_input_dir']}")
    if prepared["remote_output_dir"] != VASP_REMOTE_OUTPUT_DIR:
        raise AssertionError(f"Unexpected VASP remote output dir: {prepared['remote_output_dir']}")


def test_vasp_runtime_script_syncs_input_folder_after_sbatch_directives():
    script = "\n".join([
        "#!/bin/bash",
        "#SBATCH --job-name=vasp_relax",
        "#SBATCH --time=01:00:00",
        "test -f INCAR",
        DEFAULT_VASP_RUN,
    ])
    synced = _add_vasp_input_sync(script, "/remote/input/job1")

    assert_contains(synced, "VASP_INPUT_DIR=/remote/input/job1")
    assert_contains(synced, 'find "$VASP_INPUT_DIR" -mindepth 1 -maxdepth 1 ! -name job.sh -exec cp -R {} . \\;')

    sbatch_index = synced.index("#SBATCH --time=01:00:00")
    sync_index = synced.index("VASP_INPUT_DIR=/remote/input/job1")
    check_index = synced.index("test -f INCAR")

    if not sbatch_index < sync_index < check_index:
        raise AssertionError(f"Input sync should be inserted after SBATCH directives:\n{synced}")


def test_dangerous_vasp_request_is_rejected():
    request = "帮我生成 VASP 脚本，然后 rm -rf /tmp/data"
    answer = generate_vasp_sbatch_script(request)

    assert_contains(answer, "风险")


def test_vasp_input_validation_requires_all_files():
    with TemporaryDirectory() as tmpdir:
        for name in ["INCAR", "POSCAR", "POTCAR"]:
            (_bootstrap.Path(tmpdir) / name).write_text("test\n", encoding="utf-8")

        validation = validate_vasp_input_files(tmpdir)

        if validation["missing_files"] != ["KPOINTS"]:
            raise AssertionError(f"Expected only KPOINTS missing, got {validation}")


def test_vasp_submit_stops_when_local_inputs_missing():
    with TemporaryDirectory() as tmpdir:
        result = submit_prepared_vasp_script(
            f"#!/bin/bash\n{DEFAULT_VASP_SETUP}\n{DEFAULT_VASP_RUN}\n",
            tmpdir,
        )

        if result["success"]:
            raise AssertionError("VASP submission should fail before SSH when inputs are missing.")

        assert_contains(result["answer"], "没有找到可提交的本地 VASP 作业目录")
        assert_contains(result["answer"], "INCAR")
        assert_contains(result["answer"], "KPOINTS")


def test_resolve_vasp_job_input_dir_selects_latest_complete_job():
    with TemporaryDirectory() as jobs_dir:
        incomplete_dir = _bootstrap.Path(jobs_dir) / "incomplete"
        incomplete_dir.mkdir()
        (incomplete_dir / "INCAR").write_text("INCAR\n", encoding="utf-8")

        complete_dir = _bootstrap.Path(jobs_dir) / "complete"
        complete_dir.mkdir()

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            (complete_dir / name).write_text(f"{name}\n", encoding="utf-8")

        resolved = resolve_vasp_job_input_dir("", jobs_dir)

        if not resolved["success"]:
            raise AssertionError(f"Expected latest complete job to resolve: {resolved}")

        if resolved["input_dir"] != complete_dir:
            raise AssertionError(f"Expected {complete_dir}, got {resolved['input_dir']}")


def test_resolve_vasp_job_input_dir_uses_named_child():
    with TemporaryDirectory() as jobs_dir:
        selected_dir = _bootstrap.Path(jobs_dir) / "my_vasp_case"
        selected_dir.mkdir()

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            (selected_dir / name).write_text(f"{name}\n", encoding="utf-8")

        resolved = resolve_vasp_job_input_dir("帮我提交 VASP 作业，目录名 my_vasp_case", jobs_dir)

        if not resolved["success"]:
            raise AssertionError(f"Expected named child to resolve: {resolved}")

        if resolved["input_dir"] != selected_dir:
            raise AssertionError(f"Expected {selected_dir}, got {resolved['input_dir']}")


def test_extract_source_dir_prefers_absolute_path():
    text = "帮我提交 VASP 作业，目录 /tmp/vasp-jobs/si_static_test"
    source_dir = extract_source_dir_from_text(text)

    if source_dir != "/tmp/vasp-jobs/si_static_test":
        raise AssertionError(f"Expected absolute path, got {source_dir!r}")


def test_register_existing_vasp_job_from_text_writes_registry():
    from modules import job_registry

    original_path = job_registry.REGISTRY_PATH

    with TemporaryDirectory() as tmpdir:
        job_registry.REGISTRY_PATH = _bootstrap.Path(tmpdir) / "job_registry.json"

        try:
            result = register_existing_vasp_job_from_text(
                "登记 VASP 作业 11817144，目录名 vasp_imported_20260610_131601"
            )

            if not result["success"]:
                raise AssertionError(f"Expected VASP job registration to succeed: {result}")

            record = job_registry.get_job("11817144")

            if not record:
                raise AssertionError("Expected registered VASP job record.")

            if record["type"] != "vasp":
                raise AssertionError(f"Expected VASP record, got {record}")
        finally:
            job_registry.REGISTRY_PATH = original_path


if __name__ == "__main__":
    test_generate_vasp_script_defaults()
    test_generate_vasp_script_extracts_resources()
    test_submit_vasp_job_preview_handles_partition()
    test_dangerous_vasp_request_is_rejected()
    test_vasp_input_validation_requires_all_files()
    test_vasp_submit_stops_when_local_inputs_missing()
    test_resolve_vasp_job_input_dir_selects_latest_complete_job()
    test_resolve_vasp_job_input_dir_uses_named_child()
    test_extract_source_dir_prefers_absolute_path()
    test_register_existing_vasp_job_from_text_writes_registry()
    print("All VASP assistant checks passed.")
