import argparse
import importlib.util
import py_compile

import _bootstrap


PYTHON_FILES = [
    "app.py",
    "main.py",
    "textual_cli.py",
    "web_app.py",
    "modules/error_diagnoser.py",
    "modules/job_query.py",
    "modules/job_registry.py",
    "modules/job_submitter.py",
    "modules/knowledge_base.py",
    "modules/router.py",
    "modules/slurm_assistant.py",
    "modules/slurm_tools.py",
    "modules/vasp_assistant.py",
    "tests/test_error_diagnoser_skill.py",
    "tests/test_hpc_workflow.py",
    "tests/test_slurm_assistant.py",
    "tests/test_ssh.py",
    "tests/test_submit.py",
    "tests/test_tools.py",
    "tests/test_vasp_assistant.py",
]


def print_section(title):
    print("=" * 70)
    print(title)
    print("=" * 70)


def compile_python_files():
    print_section("1. Python syntax check")

    for relative_path in PYTHON_FILES:
        path = _bootstrap.PROJECT_ROOT / relative_path
        py_compile.compile(str(path), doraise=True)
        print(f"OK {relative_path}")


def run_slurm_assistant_checks():
    print_section("2. Slurm assistant skill checks")

    from tests import test_slurm_assistant as checks

    checks.test_basic_python_script()
    checks.test_gpu_python_script()
    checks.test_memory_shell_script()
    checks.test_missing_command_asks_for_command()
    checks.test_dangerous_command_is_rejected()

    print("OK slurm assistant skill checks passed")


def run_error_diagnoser_checks():
    print_section("3. Error diagnoser skill checks")

    from tests import test_error_diagnoser_skill as checks

    checks.test_oom_log_matches_skill_output()
    checks.test_python_module_not_found_log()
    checks.test_invalid_partition_does_not_invent_cluster_name()
    checks.test_disk_quota_does_not_recommend_rm_rf()
    checks.test_unknown_log_asks_for_more_complete_logs()

    print("OK error diagnoser skill checks passed")


def run_vasp_assistant_checks():
    print_section("4. VASP assistant skill checks")

    from tests import test_vasp_assistant as checks

    checks.test_generate_vasp_script_defaults()
    checks.test_generate_vasp_script_extracts_resources()
    checks.test_submit_vasp_job_preview_handles_partition()
    checks.test_dangerous_vasp_request_is_rejected()
    checks.test_vasp_input_validation_requires_all_files()
    checks.test_vasp_submit_stops_when_local_inputs_missing()
    checks.test_resolve_vasp_job_input_dir_selects_latest_complete_job()
    checks.test_resolve_vasp_job_input_dir_uses_named_child()
    checks.test_register_existing_vasp_job_from_text_writes_registry()

    print("OK VASP assistant skill checks passed")


def run_router_checks():
    print_section("5. Router intent checks")

    from modules.router import detect_intent

    cases = {
        "帮我提交一个作业运行 python train.py，4 核，10 分钟": "submit_job",
        "跑 monitor_cpu.py，4核，15分钟": "submit_job",
        "运行 ./job.sh，2核": "submit_job",
        "提交 /tmp/train.py，8核，1小时": "submit_job",
        "帮我生成一个 sbatch 脚本运行 python train.py": "generate_sbatch",
        "查看11814753的状态": "job_status",
        "读取11814753的输出": "job_output",
        "读取11814753的错误日志": "job_error",
        "CUDA out of memory": "diagnose_error",
        "我的任务一直 pending": "troubleshoot_job",
        "帮我生成一个 VASP 结构优化脚本": "generate_vasp_job",
        "帮我提交一个 VASP 结构优化任务，1 个节点 32 核": "submit_vasp_job",
        "登记 VASP 作业 11817144，目录名 vasp_imported_20260610_131601": "register_vasp_job",
        "列出远端 hpc-agent-jobs 里的任务编号": "list_remote_jobs",
        "清理远端作业 11817627 的文件": "cleanup_remote_job",
        "清理远端 hpc-agent-jobs 下所有作业文件": "cleanup_all_remote_jobs",
    }

    for request, expected_intent in cases.items():
        actual_intent = detect_intent(request)
        print(f"{request} -> {actual_intent}")

        if actual_intent != expected_intent:
            raise AssertionError(
                f"Expected {expected_intent!r}, got {actual_intent!r} for {request!r}"
            )

    print("OK router intent checks passed")


def run_job_query_checks():
    print_section("6. Job query parsing checks")

    from modules.job_query import extract_job_id

    cases = {
        "查看11814753的状态": "11814753",
        "读取 11814753的输出": "11814753",
        "读取 11814753 的错误日志": "11814753",
    }

    for request, expected_job_id in cases.items():
        actual_job_id = extract_job_id(request)
        print(f"{request} -> {actual_job_id}")

        if actual_job_id != expected_job_id:
            raise AssertionError(
                f"Expected job id {expected_job_id!r}, got {actual_job_id!r}"
            )

    print("OK job query parsing checks passed")


def run_submit_preview_checks():
    print_section("7. Submit preview checks")

    from main import build_submit_request_with_uploaded_files, parse_cli_attachment_paths
    from modules.job_submitter import DEFAULT_PARTITION, prepare_submit_script

    prepared = prepare_submit_script("帮我提交一个作业运行 python train.py，4 核，10 分钟")

    if not prepared["ready"]:
        raise AssertionError(f"Submit script should be ready: {prepared['message']}")

    script = prepared["script"]
    required_lines = [
        "#!/bin/bash",
        "#SBATCH --cpus-per-task=4",
        "#SBATCH --time=00:10:00",
        "python train.py",
    ]

    if DEFAULT_PARTITION:
        required_lines.append(f"#SBATCH --partition={DEFAULT_PARTITION}")
    elif "#SBATCH --partition" in script:
        raise AssertionError(f"Did not expect partition directive when DEFAULT_PARTITION is empty:\n{script}")

    for line in required_lines:
        if line not in script:
            raise AssertionError(f"Expected {line!r} in generated submit script:\n{script}")

    parsed_paths = parse_cli_attachment_paths("train.py, input.dat 'data file.txt'")
    expected_paths = ["train.py", "input.dat", "data file.txt"]

    if parsed_paths != expected_paths:
        raise AssertionError(
            f"Expected attachment paths {expected_paths!r}, got {parsed_paths!r}"
        )

    uploaded_files = [{"name": "train.py", "content": b"print('ok')\n"}]
    submit_request, inferred_command, recommendation_details = build_submit_request_with_uploaded_files(
        "我有一个作业，帮我提交上去跑，4 核，10 分钟",
        uploaded_files,
    )

    if inferred_command != "python train.py":
        raise AssertionError(f"Expected inferred command, got {inferred_command!r}")

    prepared_from_upload = prepare_submit_script(submit_request)

    if not prepared_from_upload["ready"]:
        raise AssertionError(
            f"Uploaded file submit script should be ready: {prepared_from_upload['message']}"
        )

    if "python train.py" not in prepared_from_upload["script"]:
        raise AssertionError(
            "Expected script generated from uploaded train.py to run python train.py:\n"
            + prepared_from_upload["script"]
        )

    if any(item.startswith(("CPU:", "时间:")) for item in recommendation_details):
        raise AssertionError(
            "Did not expect recommendations to override explicitly provided CPU/time:\n"
            + "\n".join(recommendation_details)
        )

    if "#SBATCH --cpus-per-task=4" not in prepared_from_upload["script"]:
        raise AssertionError("Expected explicitly provided CPU count to be preserved")

    if "#SBATCH --time=00:10:00" not in prepared_from_upload["script"]:
        raise AssertionError("Expected explicitly provided time limit to be preserved")

    gpu_files = [{"name": "train.py", "content": b"import torch\nx = x.to('cuda')\n"}]
    gpu_request, _, gpu_recommendations = build_submit_request_with_uploaded_files(
        "跑 train.py",
        gpu_files,
    )
    prepared_gpu = prepare_submit_script(gpu_request)

    if "#SBATCH --gres=gpu:1" not in prepared_gpu["script"]:
        raise AssertionError(
            "Expected GPU recommendation for CUDA Python file:\n"
            + prepared_gpu["script"]
        )

    if "#SBATCH --cpus-per-task=4" not in prepared_gpu["script"]:
        raise AssertionError(
            "Expected CPU recommendation for torch Python file:\n"
            + prepared_gpu["script"]
        )

    if not gpu_recommendations:
        raise AssertionError("Expected recommendation details for torch/cuda file")

    print("OK submit preview checks passed")


def run_env_checks():
    print_section("8. HPC env config checks")

    from modules.job_submitter import DEFAULT_PARTITION
    from modules.slurm_tools import (
        HOST,
        KEY_PATH,
        REMOTE_WORKDIR,
        USERNAME,
        VASP_REMOTE_INPUT_DIR,
        VASP_REMOTE_OUTPUT_DIR,
    )

    required_values = {
        "HPC_HOST": HOST,
        "HPC_USERNAME": USERNAME,
        "HPC_KEY_PATH": KEY_PATH,
        "HPC_REMOTE_WORKDIR": REMOTE_WORKDIR,
        "HPC_VASP_REMOTE_INPUT_DIR": VASP_REMOTE_INPUT_DIR,
        "HPC_VASP_REMOTE_OUTPUT_DIR": VASP_REMOTE_OUTPUT_DIR,
    }

    for name, value in required_values.items():
        if not value:
            raise AssertionError(f"{name} is empty")
        print(f"{name}=<set>")

    print(
        "HPC_DEFAULT_PARTITION=<set>"
        if DEFAULT_PARTITION
        else "HPC_DEFAULT_PARTITION=<empty, use cluster default>"
    )

    print("OK HPC env config checks passed")


def run_live_hpc_checks():
    print_section("9. Live HPC workflow checks")
    print("This will connect to HPC and submit a real Slurm job.")

    from tests import test_hpc_workflow

    test_hpc_workflow.main()


def main():
    parser = argparse.ArgumentParser(description="Run HPC Agent checks.")
    parser.add_argument(
        "--live-hpc",
        action="store_true",
        help="Also connect to HPC and submit a real Slurm test job.",
    )
    args = parser.parse_args()

    compile_python_files()
    run_slurm_assistant_checks()
    run_error_diagnoser_checks()
    run_vasp_assistant_checks()
    run_router_checks()
    run_job_query_checks()
    run_submit_preview_checks()
    run_env_checks()

    if args.live_hpc:
        run_live_hpc_checks()
    else:
        print_section("9. Live HPC workflow checks")
        print("SKIPPED. Use --live-hpc to submit a real Slurm test job.")

    print_section("RESULT")
    print("All requested checks passed.")


if __name__ == "__main__":
    main()
