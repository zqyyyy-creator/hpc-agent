from tests import _bootstrap  # noqa: F401
import json
import subprocess
from tempfile import TemporaryDirectory

from modules.slurm.job_submitter import (
    VASP_LOCAL_JOBS_DIR,
    VASP_LOCAL_OUTPUT_DIR,
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
from modules.routing.router import detect_intent
from modules.vasp.claude_code_reporter import (
    _build_prompt,
    _load_vasp_report_skill,
    generate_report_with_claude,
)
from modules.slurm.slurm_tools import (
    _add_vasp_input_sync,
    _has_meaningful_vasp_synced_files,
    _resolve_vasp_local_output_dir,
    _local_vasp_raw_output_dir,
    _should_sync_vasp_output_file,
)
from modules.vasp.vasp_assistant import generate_vasp_sbatch_script
from modules.vasp.vasp_report_context import generate_vasp_report_context
from modules.slurm.job_query import _local_output_dir_for_input_path


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
    assert_contains(script, "#SBATCH --time=00:10:00")
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
    request = "帮我提交一个 VASP 结构优化任务，1 个节点 32 核，运行 10 分钟"
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
    assert_contains(prepared["script"], "#SBATCH --time=00:10:00")
    assert_contains(prepared["script"], DEFAULT_VASP_SETUP)
    assert_contains(prepared["script"], DEFAULT_VASP_RUN)
    if prepared["local_jobs_dir"] != str(_bootstrap.Path(VASP_LOCAL_JOBS_DIR).resolve()):
        raise AssertionError(f"Unexpected VASP local jobs dir: {prepared['local_jobs_dir']}")
    if _bootstrap.Path(VASP_LOCAL_JOBS_DIR).expanduser().name != "vasp-jobs-input":
        raise AssertionError(f"Unexpected VASP local input dir: {VASP_LOCAL_JOBS_DIR}")
    if _bootstrap.Path(VASP_LOCAL_OUTPUT_DIR).expanduser().name != "vasp-jobs-output":
        raise AssertionError(f"Unexpected VASP local output dir: {VASP_LOCAL_OUTPUT_DIR}")
    if prepared["remote_input_dir"] != VASP_REMOTE_INPUT_DIR:
        raise AssertionError(f"Unexpected VASP remote input dir: {prepared['remote_input_dir']}")
    if prepared["remote_output_dir"] != VASP_REMOTE_OUTPUT_DIR:
        raise AssertionError(f"Unexpected VASP remote output dir: {prepared['remote_output_dir']}")


def test_vasp_submit_path_does_not_replace_runtime_command():
    request = "提交 VASP 作业，路径为 /home/qyz/vasp-jobs-input/si_static_test，帮我运行并分析"
    prepared = prepare_vasp_submit_script(request)

    if not prepared["ready"]:
        raise AssertionError(f"VASP submit script should be ready: {prepared['message']}")

    assert_contains(prepared["script"], "#SBATCH --time=00:10:00")
    assert_contains(prepared["script"], DEFAULT_VASP_RUN)
    assert_not_contains(prepared["script"], "/home/qyz/vasp-jobs-input")
    assert_not_contains(prepared["script"], "帮我运行并分析 > vasp.out")


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


def test_vasp_output_sync_file_filter_skips_large_binary_outputs():
    for name in ["OUTCAR", "OSZICAR", "vasprun.xml", "INCAR", "POSCAR", "KPOINTS", "vasp.out", "vasp_relax_123.err"]:
        if not _should_sync_vasp_output_file(name):
            raise AssertionError(f"Expected VASP output sync to include {name}")

    for name in ["WAVECAR", "CHGCAR", "AECCAR0", "AECCAR2", "POTCAR"]:
        if _should_sync_vasp_output_file(name):
            raise AssertionError(f"Expected VASP output sync to skip {name}")


def test_vasp_local_output_uses_raw_output_subdirectory():
    local_job_dir = _bootstrap.Path("/tmp/vasp-jobs-output/job-001")
    raw_output_dir = _local_vasp_raw_output_dir(local_job_dir)

    if raw_output_dir != local_job_dir / "raw_output":
        raise AssertionError(f"Expected raw output subdirectory, got {raw_output_dir}")


def test_vasp_input_path_maps_to_local_output_dir_for_reports():
    input_path = _bootstrap.Path(VASP_LOCAL_JOBS_DIR).expanduser() / "si_static_test"
    expected_output_path = _bootstrap.Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / "si_static_test"
    actual_output_path = _local_output_dir_for_input_path(input_path)

    if actual_output_path != expected_output_path:
        raise AssertionError(
            f"Expected input path to map to local output dir {expected_output_path}, "
            f"got {actual_output_path}"
        )


def test_generate_vasp_report_context_under_analysis():
    with TemporaryDirectory() as tmpdir:
        job_dir = _bootstrap.Path(tmpdir) / "job-001"
        raw_output_dir = job_dir / "raw_output"
        analysis_dir = job_dir / "analysis"
        raw_output_dir.mkdir(parents=True)
        analysis_dir.mkdir()

        (analysis_dir / "file_manifest.json").write_text(
            json.dumps({"files": [], "raw_output_dir": str(raw_output_dir)}) + "\n",
            encoding="utf-8",
        )
        (raw_output_dir / "INCAR").write_text("ENCUT = 400\nEDIFF = 1E-5\n", encoding="utf-8")
        (raw_output_dir / "KPOINTS").write_text("Automatic mesh\n0\nGamma\n3 3 3\n0 0 0\n", encoding="utf-8")
        (raw_output_dir / "POSCAR").write_text(
            "Si\n1.0\n1 0 0\n0 1 0\n0 0 1\nSi\n2\nDirect\n0 0 0\n0.25 0.25 0.25\n",
            encoding="utf-8",
        )
        (raw_output_dir / "OUTCAR").write_text("short\n", encoding="utf-8")
        (raw_output_dir / "OSZICAR").write_text("", encoding="utf-8")
        (raw_output_dir / "vasprun.xml").write_text("<modeling></modeling>\n", encoding="utf-8")
        (raw_output_dir / "vasp.err").write_text(
            "forrtl: severe (64): input conversion error, unit 10, file POTCAR\n",
            encoding="utf-8",
        )

        result = generate_vasp_report_context(job_dir)
        context_path = _bootstrap.Path(result["report_context_path"])

        if context_path != analysis_dir / "report_context.md":
            raise AssertionError(f"Expected report_context.md under analysis, got {context_path}")

        context = context_path.read_text(encoding="utf-8")
        assert_contains(context, "## INCAR Parameters")
        assert_contains(context, "ENCUT")
        assert_contains(context, "stderr reports a POTCAR input conversion error")
        assert_contains(context, "Analysis directory")


def test_generate_report_with_claude_writes_three_markdown_files():
    with TemporaryDirectory() as tmpdir:
        job_dir = _bootstrap.Path(tmpdir) / "job-001"
        analysis_dir = job_dir / "analysis"
        analysis_dir.mkdir(parents=True)
        (analysis_dir / "report_context.md").write_text(
            "# VASP Report Context\n\n## Lightweight Diagnosis\n\n- Calculation failed.\n",
            encoding="utf-8",
        )

        def fake_runner(command, **kwargs):
            if kwargs.get("timeout") != 1800:
                raise AssertionError(f"Unexpected Claude timeout: {kwargs.get('timeout')}")
            if not kwargs.get("env", {}).get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"):
                raise AssertionError("Expected Claude environment hardening flags.")
            payload = {
                "report_md": "# 用户报告\n\n计算失败。",
                "paper_methods_md": "The calculation did not complete successfully.",
                "paper_results_md": "No scientifically valid results were obtained.",
            }
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(payload, ensure_ascii=False),
                stderr="",
            )

        result = generate_report_with_claude(job_dir, runner=fake_runner)

        if not result["success"]:
            raise AssertionError(f"Expected Claude report generation to succeed: {result}")
        if "elapsed_seconds" not in result:
            raise AssertionError(f"Expected Claude report result to include elapsed seconds: {result}")

        for file_name in ["report.md", "paper_methods.md", "paper_results.md"]:
            path = analysis_dir / file_name

            if not path.is_file():
                raise AssertionError(f"Expected report file to exist: {path}")

        assert_contains((analysis_dir / "report.md").read_text(encoding="utf-8"), "计算失败")
        assert_contains(
            (analysis_dir / "paper_results.md").read_text(encoding="utf-8"),
            "No scientifically valid results",
        )


def test_resolve_vasp_local_output_dir_normalizes_stale_registry_path():
    remote_output_dir = f"{VASP_REMOTE_OUTPUT_DIR}/si_static_test"
    actual = _resolve_vasp_local_output_dir(
        remote_output_dir,
        "/tmp/legacy-output/si_static_test",
    )
    expected = _bootstrap.Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / "si_static_test"

    if actual != expected:
        raise AssertionError(
            f"Expected canonical local output dir {expected}, got {actual}"
        )


def test_has_meaningful_vasp_synced_files_rejects_job_sh_only():
    if _has_meaningful_vasp_synced_files([{"name": "job.sh"}]):
        raise AssertionError("Expected job.sh-only sync to be treated as not meaningful.")

    if not _has_meaningful_vasp_synced_files([{"name": "OUTCAR"}]):
        raise AssertionError("Expected OUTCAR to be treated as meaningful synced output.")


def test_claude_reporter_loads_vasp_report_skill():
    skill_text = _load_vasp_report_skill()

    if "name: vasp-report" not in skill_text:
        raise AssertionError("Expected vasp-report skill metadata to be available.")

    prompt = _build_prompt("# VASP Report Context\n")
    assert_contains(prompt, "Follow these vasp-report skill instructions")
    assert_contains(prompt, "paper_methods_md")
    assert_contains(prompt, "Do not read large raw files directly")


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
    from modules.slurm import job_registry

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
            if "local_output_dir" not in record:
                raise AssertionError(f"Expected VASP record to include local output dir: {record}")
            if "local_raw_output_dir" not in record:
                raise AssertionError(f"Expected VASP record to include local raw output dir: {record}")
            if "local_analysis_dir" not in record:
                raise AssertionError(f"Expected VASP record to include local analysis dir: {record}")
        finally:
            job_registry.REGISTRY_PATH = original_path


def test_sync_vasp_output_intent_requires_vasp_and_job_id():
    request = "同步 VASP 作业 11817144 输出到本地"
    if detect_intent(request) != "sync_vasp_output":
        raise AssertionError(f"Expected sync_vasp_output intent for {request!r}")


def test_generate_vasp_report_intent_prefers_report_over_script_generation():
    request = "生成 VASP 作业 si_static_test 报告"
    if detect_intent(request) != "generate_vasp_report":
        raise AssertionError(f"Expected generate_vasp_report intent for {request!r}")


def test_analyze_vasp_job_intent():
    request = "一键分析 VASP 作业 si_static_test"
    if detect_intent(request) != "analyze_vasp_job":
        raise AssertionError(f"Expected analyze_vasp_job intent for {request!r}")


def test_outcar_parser_extracts_deterministic_energies():
    from modules.vasp.vasp_outcar_parser import parse_vasp_results, format_facts_block

    outcar = """\
FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)
---------------------------------------------------
free  energy   TOTEN  =        -12.34567891 eV

energy  without entropy=      -12.34000000  energy(sigma->0) =      -12.34300000
"""
    oszicar = """\
DAV:   1    -0.500000000000E+01   -0.50000E+01   -0.50000E+01   384   0.152E+02
DAV:   2    -0.120000000000E+02   -0.70000E+01   -0.70000E+01   576   0.178E+01
   1 F= -.12345679E+02 E0= -.12343000E+02  d E =-.123456E-02
"""
    with TemporaryDirectory() as tmpdir:
        raw_dir = _bootstrap.Path(tmpdir)
        (raw_dir / "OUTCAR").write_text(outcar, encoding="utf-8")
        (raw_dir / "OSZICAR").write_text(oszicar, encoding="utf-8")

        facts = parse_vasp_results(raw_dir)
        block = format_facts_block(facts)

    if facts["energy"]["toten"] != -12.34567891:
        raise AssertionError(f"Expected TOTEN=-12.34567891, got {facts['energy']['toten']}")
    if facts["oszicar"]["F"] != -12.345679:
        raise AssertionError(f"Expected OSZICAR F=-12.345679, got {facts['oszicar']['F']}")
    if facts["oszicar"]["iterations"] != 2:
        raise AssertionError(f"Expected 2 iterations, got {facts['oszicar']['iterations']}")
    if facts["convergence"]["converged"]:
        raise AssertionError("Expected not converged (no 'reached required accuracy' in output)")

    assert_contains(block, "**-12.34567891**")
    assert_contains(block, "**-12.34567900**")
    assert_contains(block, "authoritative source")
    assert_contains(block, "**2**")


def test_outcar_parser_handles_converged_calculation():
    from modules.vasp.vasp_outcar_parser import parse_vasp_results

    outcar = """\
FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)
---------------------------------------------------
free  energy   TOTEN  =        -5.00000000 eV

reached required accuracy - stopping structural energy minimisation

E-fermi :   2.7491

NELECT =       8.0000    total number of electrons

VOLUME and BASIS-vectors are now :
volume of cell :       56.62

in kB     300.00   300.00   300.00   370.00   370.00   370.00
external pressure =      300.00 kB

POSITION                                       TOTAL-FORCE (eV/Angst)
     0.00000      0.00000      0.00000         0.000000      0.000000      0.000000
     0.96000      0.96000      0.96000         0.000000      0.000000      0.000000

Total CPU time used (sec):        5.000
Elapsed time (sec):       10.000
Maximum memory used (kb):      100000.

k-point   1 :       0.0000    0.0000    0.0000
 band No.  band energies     occupation
     1      -8.0000      2.00000
     2       1.5000      2.00000
     3       2.0000      2.00000
     4       3.0000      2.00000
     5       4.0000      0.00000
     6       5.0000      0.00000
"""
    with TemporaryDirectory() as tmpdir:
        raw_dir = _bootstrap.Path(tmpdir)
        (raw_dir / "OUTCAR").write_text(outcar, encoding="utf-8")
        (raw_dir / "OSZICAR").write_text("   1 F= -.50000000E+01 E0= -.50000000E+01  d E =0.000000E+00", encoding="utf-8")

        facts = parse_vasp_results(raw_dir)

    if not facts["convergence"]["converged"]:
        raise AssertionError("Expected converged (reached required accuracy)")
    if facts["energy"]["toten"] != -5.0:
        raise AssertionError(f"Expected TOTEN=-5.0, got {facts['energy']['toten']}")
    if facts["electronic"]["efermi"] != 2.7491:
        raise AssertionError(f"Expected E-fermi=2.7491, got {facts['electronic']['efermi']}")
    if facts["cell"]["volume"] != 56.62:
        raise AssertionError(f"Expected volume=56.62, got {facts['cell']['volume']}")
    if facts["forces"]["max_force_eV_A"] != 0.0:
        raise AssertionError(f"Expected max force=0.0, got {facts['forces']['max_force_eV_A']}")
    if facts["timing"]["total_cpu_time_sec"] != 5.0:
        raise AssertionError(f"Expected total CPU time=5.0, got {facts['timing']['total_cpu_time_sec']}")
    if facts["band_structure"]["band_gap_eV"] != 1.0:
        raise AssertionError(f"Expected band gap=1.0 (VBM=4.0, CBM=5.0), got {facts['band_structure']['band_gap_eV']}")
    if facts["stress"]["stress_kB"] != [300.0, 300.0, 300.0, 370.0, 370.0, 370.0]:
        raise AssertionError(f"Unexpected stress tensor: {facts['stress']['stress_kB']}")


def test_outcar_parser_reports_failure_on_missing_outcar():
    from modules.vasp.vasp_outcar_parser import parse_vasp_results

    with TemporaryDirectory() as tmpdir:
        facts = parse_vasp_results(_bootstrap.Path(tmpdir))

    if "error" not in facts:
        raise AssertionError(f"Expected error when OUTCAR is missing, got {facts}")


if __name__ == "__main__":
    test_generate_vasp_script_defaults()
    test_generate_vasp_script_extracts_resources()
    test_submit_vasp_job_preview_handles_partition()
    test_vasp_submit_path_does_not_replace_runtime_command()
    test_vasp_runtime_script_syncs_input_folder_after_sbatch_directives()
    test_vasp_output_sync_file_filter_skips_large_binary_outputs()
    test_vasp_local_output_uses_raw_output_subdirectory()
    test_vasp_input_path_maps_to_local_output_dir_for_reports()
    test_generate_vasp_report_context_under_analysis()
    test_generate_report_with_claude_writes_three_markdown_files()
    test_claude_reporter_loads_vasp_report_skill()
    test_dangerous_vasp_request_is_rejected()
    test_vasp_input_validation_requires_all_files()
    test_vasp_submit_stops_when_local_inputs_missing()
    test_resolve_vasp_job_input_dir_selects_latest_complete_job()
    test_resolve_vasp_job_input_dir_uses_named_child()
    test_extract_source_dir_prefers_absolute_path()
    test_register_existing_vasp_job_from_text_writes_registry()
    test_sync_vasp_output_intent_requires_vasp_and_job_id()
    test_generate_vasp_report_intent_prefers_report_over_script_generation()
    test_analyze_vasp_job_intent()
    test_outcar_parser_extracts_deterministic_energies()
    test_outcar_parser_handles_converged_calculation()
    test_outcar_parser_reports_failure_on_missing_outcar()
    print("All VASP assistant checks passed.")
