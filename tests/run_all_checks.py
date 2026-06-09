import argparse
import importlib.util
import py_compile

import _bootstrap


PYTHON_FILES = [
    "app.py",
    "main.py",
    "web_app.py",
    "modules/error_diagnoser.py",
    "modules/job_query.py",
    "modules/job_submitter.py",
    "modules/knowledge_base.py",
    "modules/router.py",
    "modules/slurm_assistant.py",
    "modules/slurm_tools.py",
    "tests/test_error_diagnoser_skill.py",
    "tests/test_hpc_workflow.py",
    "tests/test_slurm_assistant.py",
    "tests/test_ssh.py",
    "tests/test_submit.py",
    "tests/test_tools.py",
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


def run_router_checks():
    print_section("4. Router intent checks")

    from modules.router import detect_intent

    cases = {
        "帮我提交一个作业运行 python train.py，4 核，10 分钟": "submit_job",
        "帮我生成一个 sbatch 脚本运行 python train.py": "generate_sbatch",
        "查看11814753的状态": "job_status",
        "读取11814753的输出": "job_output",
        "读取11814753的错误日志": "job_error",
        "CUDA out of memory": "diagnose_error",
        "我的任务一直 pending": "troubleshoot_job",
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
    print_section("5. Job query parsing checks")

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
    print_section("6. Submit preview checks")

    from modules.job_submitter import DEFAULT_PARTITION, prepare_submit_script

    prepared = prepare_submit_script("帮我提交一个作业运行 python train.py，4 核，10 分钟")

    if not prepared["ready"]:
        raise AssertionError(f"Submit script should be ready: {prepared['message']}")

    script = prepared["script"]
    required_lines = [
        "#!/bin/bash",
        f"#SBATCH --partition={DEFAULT_PARTITION}",
        "#SBATCH --cpus-per-task=4",
        "#SBATCH --time=00:10:00",
        "python train.py",
    ]

    for line in required_lines:
        if line not in script:
            raise AssertionError(f"Expected {line!r} in generated submit script:\n{script}")

    print(script)
    print("OK submit preview checks passed")


def run_env_checks():
    print_section("7. HPC env config checks")

    from modules.job_submitter import DEFAULT_PARTITION
    from modules.slurm_tools import HOST, KEY_PATH, REMOTE_WORKDIR, USERNAME

    values = {
        "HPC_HOST": HOST,
        "HPC_USERNAME": USERNAME,
        "HPC_KEY_PATH": KEY_PATH,
        "HPC_REMOTE_WORKDIR": REMOTE_WORKDIR,
        "HPC_DEFAULT_PARTITION": DEFAULT_PARTITION,
    }

    for name, value in values.items():
        if not value:
            raise AssertionError(f"{name} is empty")
        print(f"{name}={value}")

    print("OK HPC env config checks passed")


def run_live_hpc_checks():
    print_section("8. Live HPC workflow checks")
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
    run_router_checks()
    run_job_query_checks()
    run_submit_preview_checks()
    run_env_checks()

    if args.live_hpc:
        run_live_hpc_checks()
    else:
        print_section("8. Live HPC workflow checks")
        print("SKIPPED. Use --live-hpc to submit a real Slurm test job.")

    print_section("RESULT")
    print("All requested checks passed.")


if __name__ == "__main__":
    main()
