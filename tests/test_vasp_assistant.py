import _bootstrap  # noqa: F401
from tempfile import TemporaryDirectory

from modules.job_submitter import (
    VASP_PARTITION,
    create_vasp_local_job_dir,
    create_vasp_inputs_from_text,
    generate_vasp_template_inputs,
    extract_source_dir_from_text,
    import_vasp_inputs_from_dir,
    parse_vasp_input_blocks,
    prepare_vasp_submit_script,
    register_existing_vasp_job_from_text,
    resolve_vasp_job_input_dir,
    submit_prepared_vasp_script,
    validate_vasp_input_files,
)
from modules.router import detect_intent
from modules.vasp_assistant import generate_vasp_sbatch_script


def assert_contains(text: str, expected: str):
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in:\n{text}")


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
    assert_contains(script, "vasp_std > vasp.out")


def test_generate_vasp_script_extracts_resources():
    request = "帮我生成 VASP 脚本，2 个节点，每节点 64 核，运行 48 小时，命令是 mpirun vasp_std"
    script = generate_vasp_sbatch_script(request)

    assert detect_intent(request) == "generate_vasp_job"
    assert_contains(script, "#SBATCH --nodes=2")
    assert_contains(script, "#SBATCH --ntasks-per-node=64")
    assert_contains(script, "#SBATCH --time=48:00:00")
    assert_contains(script, "mpirun vasp_std > vasp.out")


def test_submit_vasp_job_preview_adds_partition():
    request = "帮我提交一个 VASP 结构优化任务，1 个节点 32 核，运行 24 小时，命令是 vasp_std"
    prepared = prepare_vasp_submit_script(request)

    if not prepared["ready"]:
        raise AssertionError(f"VASP submit script should be ready: {prepared['message']}")

    assert detect_intent(request) == "submit_vasp_job"
    assert_contains(prepared["script"], f"#SBATCH --partition={VASP_PARTITION}")
    assert_contains(prepared["script"], "#SBATCH --nodes=1")
    assert_contains(prepared["script"], "#SBATCH --ntasks-per-node=32")
    assert_contains(prepared["script"], "vasp_std > vasp.out")


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
        result = submit_prepared_vasp_script("#!/bin/bash\nvasp_std > vasp.out\n", tmpdir)

        if result["success"]:
            raise AssertionError("VASP submission should fail before SSH when inputs are missing.")

        assert_contains(result["answer"], "没有找到可提交的本地 VASP 作业目录")
        assert_contains(result["answer"], "INCAR")
        assert_contains(result["answer"], "KPOINTS")


def test_create_vasp_local_job_dir_archives_inputs_and_job_script():
    script = "#!/bin/bash\n#SBATCH --job-name=vasp_relax\nvasp_std > vasp.out\n"

    with TemporaryDirectory() as input_dir, TemporaryDirectory() as jobs_dir:
        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            (_bootstrap.Path(input_dir) / name).write_text(f"{name}\n", encoding="utf-8")

        archive = create_vasp_local_job_dir(script, input_dir, jobs_dir)
        local_job_dir = archive["local_job_dir"]

        if not local_job_dir.is_dir():
            raise AssertionError(f"Expected local job dir to exist: {local_job_dir}")

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS", "job.sh"]:
            path = local_job_dir / name
            if not path.is_file():
                raise AssertionError(f"Expected archived file to exist: {path}")

        assert_contains((local_job_dir / "job.sh").read_text(encoding="utf-8"), "vasp_std > vasp.out")


def test_parse_vasp_input_blocks():
    text = """
请生成 VASP 输入文件
```INCAR
SYSTEM = test
ENCUT = 520
```
```POSCAR
Si
1.0
```
```POTCAR
POTCAR content
```
```KPOINTS
Automatic mesh
```
"""
    inputs = parse_vasp_input_blocks(text)

    if set(inputs) != {"INCAR", "POSCAR", "POTCAR", "KPOINTS"}:
        raise AssertionError(f"Unexpected parsed files: {inputs.keys()}")

    assert_contains(inputs["INCAR"], "ENCUT = 520")
    assert_contains(inputs["POTCAR"], "POTCAR content")


def test_create_vasp_inputs_from_text_writes_files():
    text = """
生成 VASP 输入文件
```INCAR
SYSTEM = test
```
```POSCAR
Si
1.0
```
```POTCAR
POTCAR content
```
```KPOINTS
Automatic mesh
```
"""

    with TemporaryDirectory() as jobs_dir:
        result = create_vasp_inputs_from_text(text, jobs_dir, "si_relax")

        if not result["success"]:
            raise AssertionError(f"Expected input files to be written: {result}")

        local_input_dir = result["local_input_dir"]
        if local_input_dir.parent != _bootstrap.Path(jobs_dir):
            raise AssertionError(f"Expected files under jobs dir, got {local_input_dir}")

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            if not (local_input_dir / name).is_file():
                raise AssertionError(f"Expected generated file: {local_input_dir / name}")

        assert_contains((local_input_dir / "INCAR").read_text(encoding="utf-8"), "SYSTEM = test")


def test_create_vasp_inputs_from_text_requires_all_files():
    text = """
```INCAR
SYSTEM = test
```
"""

    with TemporaryDirectory() as jobs_dir:
        result = create_vasp_inputs_from_text(text, jobs_dir, "missing")

        if result["success"]:
            raise AssertionError("Expected missing files to fail.")

        if result["missing_files"] != ["POSCAR", "POTCAR", "KPOINTS"]:
            raise AssertionError(f"Unexpected missing files: {result['missing_files']}")


def test_import_vasp_inputs_from_dir_copies_all_files():
    with TemporaryDirectory() as source_dir, TemporaryDirectory() as jobs_dir:
        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            (_bootstrap.Path(source_dir) / name).write_text(f"{name}\n", encoding="utf-8")

        result = import_vasp_inputs_from_dir(source_dir, jobs_dir, "imported")

        if not result["success"]:
            raise AssertionError(f"Expected import to succeed: {result}")

        local_input_dir = result["local_input_dir"]

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            path = local_input_dir / name
            if not path.is_file():
                raise AssertionError(f"Expected imported file: {path}")


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
    text = "请从目录导入 VASP 输入文件: /home/lenovo/vasp-jobs-input"
    source_dir = extract_source_dir_from_text(text)

    if source_dir != "/home/lenovo/vasp-jobs-input":
        raise AssertionError(f"Expected absolute path, got {source_dir!r}")


def test_generate_vasp_template_inputs_does_not_fake_potcar():
    with TemporaryDirectory() as jobs_dir:
        result = generate_vasp_template_inputs("请 Agent 辅助生成 Si 结构优化 VASP 输入模板", jobs_dir)

        if not result["success"]:
            raise AssertionError(f"Expected template generation to succeed: {result}")

        local_input_dir = result["local_input_dir"]

        for name in ["INCAR", "POSCAR", "KPOINTS"]:
            if not (local_input_dir / name).is_file():
                raise AssertionError(f"Expected generated template file: {name}")

        if (local_input_dir / "POTCAR").exists():
            raise AssertionError("Agent must not generate fake POTCAR content.")

        if "POTCAR" not in result["missing_files"]:
            raise AssertionError(f"Expected POTCAR to be missing: {result}")


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
    test_submit_vasp_job_preview_adds_partition()
    test_dangerous_vasp_request_is_rejected()
    test_vasp_input_validation_requires_all_files()
    test_vasp_submit_stops_when_local_inputs_missing()
    test_create_vasp_local_job_dir_archives_inputs_and_job_script()
    test_parse_vasp_input_blocks()
    test_create_vasp_inputs_from_text_writes_files()
    test_create_vasp_inputs_from_text_requires_all_files()
    test_import_vasp_inputs_from_dir_copies_all_files()
    test_resolve_vasp_job_input_dir_selects_latest_complete_job()
    test_resolve_vasp_job_input_dir_uses_named_child()
    test_extract_source_dir_prefers_absolute_path()
    test_generate_vasp_template_inputs_does_not_fake_potcar()
    test_register_existing_vasp_job_from_text_writes_registry()
    print("All VASP assistant checks passed.")
