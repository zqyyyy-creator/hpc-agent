import argparse
import importlib.util
import py_compile

import _bootstrap


PYTHON_FILES = [
    "app.py",
    "textual_cli.py",
    "tools/route_debug.py",
    "modules/core/agent_runtime.py",
    "modules/core/confirmed_actions.py",
    "modules/core/conversation_state.py",
    "modules/core/hpc_config.py",
    "modules/core/llm_fallback.py",
    "modules/core/tool_calling.py",
    "modules/knowledge/error_diagnoser.py",
    "modules/knowledge/knowledge_base.py",
    "modules/routing/intent_classifier.py",
    "modules/routing/router.py",
    "modules/routing/tool_dispatcher.py",
    "modules/slurm/hpc_test_files.py",
    "modules/slurm/job_cleanup.py",
    "modules/slurm/job_lifecycle.py",
    "modules/slurm/job_listing.py",
    "modules/slurm/job_logs.py",
    "modules/slurm/job_monitor.py",
    "modules/slurm/job_query.py",
    "modules/slurm/job_registry.py",
    "modules/slurm/job_submission.py",
    "modules/slurm/job_submitter.py",
    "modules/slurm/remote.py",
    "modules/slurm/remote_utils.py",
    "modules/slurm/slurm_assistant.py",
    "modules/slurm/slurm_tools.py",
    "modules/slurm/submit_attachments.py",
    "modules/slurm/vasp_sync.py",
    "modules/tui/tui_formatters.py",
    "modules/tui/tui_helpers.py",
    "modules/tui/tui_monitor.py",
    "modules/tui/tui_vasp_workflow.py",
    "modules/vasp/claude_code_reporter.py",
    "modules/vasp/vasp_assistant.py",
    "modules/vasp/vasp_monitor.py",
    "modules/vasp/vasp_outcar_parser.py",
    "modules/vasp/vasp_report_context.py",
    "tests/core/test_agent_runtime.py",
    "tests/core/test_confirmed_actions.py",
    "tests/core/test_conversation_state.py",
    "tests/core/test_environment_status.py",
    "tests/core/test_tool_calling.py",
    "tests/knowledge/test_error_diagnoser_skill.py",
    "tests/knowledge/test_knowledge_base_context.py",
    "tests/routing/test_route_planner.py",
    "tests/routing/test_route_cases_fixture.py",
    "tests/routing/test_router_negative.py",
    "tests/routing/test_tool_dispatcher.py",
    "tests/slurm/test_cleanup_tool_calling.py",
    "tests/slurm/test_hpc_workflow.py",
    "tests/slurm/test_hpc_test_files.py",
    "tests/slurm/test_job_query_tool_calling.py",
    "tests/slurm/test_job_lifecycle.py",
    "tests/slurm/test_slurm_assistant.py",
    "tests/slurm/test_slurm_tool_calling.py",
    "tests/slurm/test_ssh.py",
    "tests/slurm/test_submit.py",
    "tests/slurm/test_tools.py",
    "tests/vasp/test_vasp_assistant.py",
    "tests/vasp/test_vasp_monitor.py",
    "tests/vasp/test_vasp_postprocess_tool_calling.py",
    "tests/vasp/test_vasp_tool_calling.py",
]


def print_section(title):
    print("=" * 70)
    print(title)
    print("=" * 70)


def compile_python_files():
    for relative_path in PYTHON_FILES:
        path = _bootstrap.PROJECT_ROOT / relative_path
        py_compile.compile(str(path), doraise=True)
        print(f"OK {relative_path}")


def run_slurm_assistant_checks():
    from tests.slurm import test_slurm_assistant as checks

    checks.test_basic_python_script()
    checks.test_gpu_python_script()
    checks.test_memory_shell_script()
    checks.test_missing_command_still_generates()
    checks.test_hpc_submission_smoke_test_generates_hostname_script()
    checks.test_dangerous_command_is_rejected()
    checks.test_resource_question_is_not_treated_as_submission()

    print("OK slurm assistant skill checks passed")


def run_agent_runtime_checks():
    from tests.core import test_agent_runtime as checks
    from tests.core import test_environment_status as env_checks

    for check in [
        checks.test_can_answer_intent_marks_only_answer_intents,
        checks.test_can_preview_cleanup_intent_marks_cleanup_intents,
        checks.test_can_preview_submit_intent_marks_submit_intents,
        checks.test_execute_clarify_intent_does_not_need_llm,
        checks.test_execute_diagnose_intent_uses_injected_diagnoser,
        checks.test_execute_diagnose_job_intent_uses_job_diagnosis,
        checks.test_execute_current_config_intent_reports_models,
        checks.test_execute_archive_preview_returns_pending_action,
        checks.test_execute_restore_preview_returns_pending_action,
        checks.test_execute_job_output_returns_job_id_and_live_log,
        checks.test_execute_cleanup_preview_returns_pending_payload,
        checks.test_execute_submit_preview_returns_pending_submission,
        checks.test_execute_hpc_submission_test_returns_pending_submission,
        checks.test_execute_vasp_submit_preview_keeps_auto_analyze,
        env_checks.test_current_model_config_masks_api_key,
        env_checks.test_hpc_environment_check_uses_injected_remote_runner,
    ]:
        check()

    print("OK agent runtime checks passed")


def run_hpc_test_file_checks():
    from tests.slurm import test_hpc_test_files as checks

    checks.test_sleep_test_file_defaults_to_test_py()
    checks.test_variable_sleep_seconds_are_supported()
    checks.test_hostname_shell_test_file_uses_requested_name()
    checks.test_hostname_natural_language_variants()
    checks.test_mpi_hostname_test_file()
    checks.test_mpi_hostname_natural_language_with_task_count()
    checks.test_sleep_test_file_and_run_uses_normal_submit_flow()
    checks.test_mpi_test_file_and_run_requests_four_cpus()
    checks.test_variable_sleep_run_uses_dynamic_job_time()
    checks.test_rule_based_tool_call_for_test_job()
    checks.test_llm_tool_call_fallback_for_fuzzy_sleep_request()
    checks.test_ambiguous_test_job_asks_for_clarification()
    checks.test_llm_tool_call_rejects_unsafe_file_name()
    checks.test_execute_test_job_tool_call_returns_tool_result()

    print("OK HPC test file checks passed")


def run_tool_calling_checks():
    from tests.core import test_tool_calling as checks

    checks.test_tool_call_roundtrip()
    checks.test_ensure_allowed_tool_rejects_unknown_tool()
    checks.test_tool_registry_executes_registered_handler()

    print("OK tool calling framework checks passed")


def run_confirmed_action_checks():
    from tests.core import test_confirmed_actions as checks

    checks.test_confirmed_slurm_submit_records_job()
    checks.test_confirmed_vasp_submit_records_vasp_job()
    checks.test_confirmed_cleanup_returns_answer_and_targets()
    checks.test_confirmed_archive_job_records_returns_archive_result()
    checks.test_confirmed_restore_job_records_returns_restore_result()
    checks.test_unknown_confirmed_action_is_rejected()

    print("OK confirmed action checks passed")


def run_conversation_state_checks():
    from tests.core import test_conversation_state as checks

    checks.test_record_job_creates_structured_recent_entry()
    checks.test_record_job_updates_existing_job_without_duplicate()
    checks.test_resolve_latest_job_by_kind()
    checks.test_resolve_ordinal_job_reference()
    checks.test_resolve_by_source()
    checks.test_resolve_vasp_job_id_prefers_vasp_context()
    checks.test_pending_action_and_generic_confirmation_memory()
    checks.test_answer_context_summary_includes_recent_turns_and_jobs()

    print("OK conversation state checks passed")


def run_knowledge_base_context_checks():
    from tests.knowledge import test_knowledge_base_context as checks

    checks.test_build_ask_llm_messages_includes_conversation_context()

    print("OK knowledge base context checks passed")


def run_tool_dispatcher_checks():
    from tests.routing import test_tool_dispatcher as checks

    checks.test_dispatcher_ignores_non_tool_intent()
    checks.test_dispatcher_handles_slurm_submit_preview()
    checks.test_dispatcher_handles_vasp_submit_preview()
    checks.test_dispatcher_handles_test_file_request_with_injected_handler()
    checks.test_dispatcher_handles_job_query_with_state()
    checks.test_dispatcher_handles_cleanup_preview()
    checks.test_dispatcher_handles_vasp_postprocess()
    checks.test_llm_classified_test_file_preserves_structured_slots()
    checks.test_llm_classified_vasp_cleanup_preserves_selector_and_scope()
    checks.test_can_dispatch_intent_marks_tool_intents()

    print("OK tool dispatcher checks passed")


def run_slurm_tool_calling_checks():
    from tests.slurm import test_slurm_tool_calling as checks

    checks.test_prepare_slurm_job_tool_call_extracts_arguments()
    checks.test_execute_prepare_slurm_job_tool_call_returns_preview_result()
    checks.test_prepare_submit_script_keeps_existing_response_shape()
    checks.test_prepare_slurm_job_tool_call_missing_command_matches_existing_message()

    print("OK Slurm tool calling checks passed")


def run_job_query_tool_calling_checks():
    from tests.slurm import test_job_query_tool_calling as checks

    checks.test_make_job_query_tool_call_with_explicit_job_id()
    checks.test_job_query_uses_last_job_id_from_state()
    checks.test_job_query_without_context_asks_for_job_id()
    checks.test_execute_job_query_tool_call_uses_injected_query_function()
    checks.test_router_detects_last_job_references()
    checks.test_diagnose_job_request_returns_next_steps()

    print("OK job query tool calling checks passed")


def run_cleanup_tool_calling_checks():
    from tests.slurm import test_cleanup_tool_calling as checks

    checks.test_make_cleanup_tool_call_for_regular_job()
    checks.test_cleanup_regular_job_prepare_result()
    checks.test_cleanup_all_regular_jobs_requires_strong_confirmation()
    checks.test_cleanup_vasp_job_scope_and_selector()
    checks.test_cleanup_all_vasp_jobs_requires_strong_confirmation()
    checks.test_generic_vasp_directory_cleanup_routes_to_all_vasp_cleanup()
    checks.test_cleanup_missing_job_id_asks_for_clarification()

    print("OK cleanup tool calling checks passed")


def run_vasp_tool_calling_checks():
    from tests.vasp import test_vasp_tool_calling as checks

    checks.test_prepare_vasp_job_tool_call_extracts_context()
    checks.test_execute_prepare_vasp_job_tool_call_returns_preview_result()
    checks.test_prepare_vasp_submit_script_keeps_existing_response_shape()
    checks.test_prepare_vasp_submit_script_rejects_dangerous_request()

    print("OK VASP tool calling checks passed")


def run_vasp_postprocess_tool_calling_checks():
    from tests.vasp import test_vasp_postprocess_tool_calling as checks

    checks.test_make_register_vasp_tool_call()
    checks.test_register_vasp_tool_call_records_state()
    checks.test_sync_vasp_output_uses_explicit_job_id()
    checks.test_sync_vasp_output_uses_last_vasp_job_id()
    checks.test_sync_vasp_output_without_context_asks_for_job_id()
    checks.test_register_vasp_requires_selector()

    print("OK VASP postprocess tool calling checks passed")


def run_error_diagnoser_checks():
    from tests.knowledge import test_error_diagnoser_skill as checks

    checks.test_oom_log_matches_skill_output()
    checks.test_python_module_not_found_log()
    checks.test_invalid_partition_does_not_invent_cluster_name()
    checks.test_disk_quota_does_not_recommend_rm_rf()
    checks.test_unknown_log_asks_for_more_complete_logs()

    print("OK error diagnoser skill checks passed")


def run_vasp_assistant_checks():
    from tests.vasp import test_vasp_assistant as checks
    from tests.vasp import test_vasp_monitor as monitor_checks
    import textual_cli

    checks.test_generate_vasp_script_defaults()
    checks.test_generate_vasp_script_extracts_resources()
    checks.test_parse_potcar_entries_extracts_metadata()
    checks.test_generate_vasp_inputs_from_single_element_potcar_writes_files()
    checks.test_generate_vasp_inputs_request_resolves_named_job_dir()
    checks.test_generate_vasp_inputs_does_not_overwrite_without_explicit_request()
    checks.test_submit_vasp_job_preview_handles_partition()
    checks.test_vasp_submit_path_does_not_replace_runtime_command()
    checks.test_dangerous_vasp_request_is_rejected()
    checks.test_vasp_input_validation_requires_all_files()
    checks.test_vasp_submit_stops_when_local_inputs_missing()
    checks.test_resolve_vasp_job_input_dir_selects_latest_complete_job()
    checks.test_resolve_vasp_job_input_dir_uses_named_child()
    checks.test_register_existing_vasp_job_from_text_writes_registry()
    checks.test_generate_vasp_report_context_under_analysis()
    checks.test_generate_report_with_claude_writes_three_markdown_files()
    checks.test_resolve_vasp_local_output_dir_normalizes_stale_registry_path()
    checks.test_claude_reporter_loads_vasp_report_skill()
    checks.test_vasp_input_path_maps_to_local_output_dir_for_reports()
    checks.test_generate_vasp_report_intent_prefers_report_over_script_generation()
    checks.test_analyze_vasp_job_intent()
    monitor_checks.test_potcar_input_conversion_is_error()
    monitor_checks.test_brmix_warning_is_warning()
    monitor_checks.test_empty_oszicar_is_suppressed_for_running_job()
    monitor_checks.test_empty_oszicar_is_warning_for_terminal_job()
    monitor_checks.test_non_vasp_directory_stays_unknown()

    if not textual_cli._is_vasp_long_workflow_request("提交 VASP 作业，路径为 /tmp/si，帮我运行并分析"):
        raise AssertionError("Expected VASP long workflow request to be detected")
    if textual_cli._is_vasp_long_workflow_request("提交 VASP 作业，路径为 /tmp/si"):
        raise AssertionError("Did not expect plain VASP submit request to auto-analyze")

    print("OK VASP assistant skill checks passed")


def run_router_checks():
    from tests.routing import test_route_cases_fixture as checks

    checks.test_route_cases_fixture_schema()
    checks.test_route_cases_fixture()
    checks.test_route_cases_explainable()

    print("OK router intent checks passed")


def run_router_negative_checks():
    from tests.routing import test_router_negative as checks

    checks.test_howto_questions_do_not_trigger_actions()
    checks.test_resource_questions_beat_submit_phrases()
    checks.test_unrelated_delete_or_local_cleanup_is_not_remote_cleanup()
    checks.test_negated_actions_change_or_block_intent()
    checks.test_ambiguous_requests_ask_for_clarification()
    checks.test_route_decision_exposes_reason_keywords_and_risk()
    checks.test_analyze_job_id_routes_to_vasp_when_registry_marks_job_as_vasp()
    checks.test_analyze_last_job_routes_to_vasp_when_recent_context_marks_job_as_vasp()

    print("OK router negative checks passed")


def run_route_planner_checks():
    from tests.routing import test_route_planner as checks

    checks.test_conditional_vasp_workflow_becomes_plan()
    checks.test_sequential_regular_workflow_becomes_plan()
    checks.test_single_vasp_submit_and_analyze_phrase_stays_single_intent()
    checks.test_plan_formatter_mentions_no_auto_execution()
    checks.test_confirm_step_resolves_to_saved_route_text()
    checks.test_confirm_second_step_keeps_vasp_context()
    checks.test_execute_all_selection_is_supported_for_safe_plan()
    checks.test_execute_all_rejects_confirm_required_plan()

    print("OK route planner checks passed")


def run_job_query_checks():
    from modules.slurm.job_query import extract_job_id

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


def run_job_lifecycle_checks():
    from tests.slurm import test_job_lifecycle as checks

    checks.test_recent_jobs_lists_latest_local_records()
    checks.test_vasp_jobs_filters_non_vasp_records()
    checks.test_job_detail_reports_paths_and_next_steps()
    checks.test_job_record_status_summarizes_registry()
    checks.test_archive_job_records_preview_keeps_recent_without_writing()
    checks.test_archive_job_records_preview_requires_keep_count()
    checks.test_archive_job_records_moves_records_to_archive_file()
    checks.test_job_record_archives_lists_archive_files()
    checks.test_restore_job_records_preview_and_restore_missing_records()

    print("OK job lifecycle checks passed")


def run_submit_preview_checks():
    from modules.slurm.job_submitter import DEFAULT_PARTITION, prepare_submit_script
    from modules.slurm.submit_attachments import build_submit_request_with_uploaded_files, parse_cli_attachment_paths

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

    if inferred_command != "python3 train.py":
        raise AssertionError(f"Expected inferred command, got {inferred_command!r}")

    prepared_from_upload = prepare_submit_script(submit_request)

    if not prepared_from_upload["ready"]:
        raise AssertionError(
            f"Uploaded file submit script should be ready: {prepared_from_upload['message']}"
        )

    if "python3 train.py" not in prepared_from_upload["script"]:
        raise AssertionError(
            "Expected script generated from uploaded train.py to run python3 train.py:\n"
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
    from modules.slurm.job_submitter import DEFAULT_PARTITION
    from modules.slurm.slurm_tools import (
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
    print("This will connect to HPC and submit a real Slurm job.")

    from tests.slurm import test_hpc_workflow

    test_hpc_workflow.main()


CHECKS = [
    ("1. Python syntax check", compile_python_files),
    ("2. Slurm assistant skill checks", run_slurm_assistant_checks),
    ("2b. Agent runtime checks", run_agent_runtime_checks),
    ("3. HPC test file checks", run_hpc_test_file_checks),
    ("4. Tool calling framework checks", run_tool_calling_checks),
    ("5. Confirmed action checks", run_confirmed_action_checks),
    ("6. Conversation state checks", run_conversation_state_checks),
    ("6b. Knowledge base context checks", run_knowledge_base_context_checks),
    ("7. Tool dispatcher checks", run_tool_dispatcher_checks),
    ("8. Slurm tool calling checks", run_slurm_tool_calling_checks),
    ("9. Job query tool calling checks", run_job_query_tool_calling_checks),
    ("9b. Job lifecycle checks", run_job_lifecycle_checks),
    ("10. Cleanup tool calling checks", run_cleanup_tool_calling_checks),
    ("11. VASP tool calling checks", run_vasp_tool_calling_checks),
    ("12. VASP postprocess tool calling checks", run_vasp_postprocess_tool_calling_checks),
    ("13. Error diagnoser skill checks", run_error_diagnoser_checks),
    ("14. VASP assistant skill checks", run_vasp_assistant_checks),
    ("15. Router intent checks", run_router_checks),
    ("16. Router negative checks", run_router_negative_checks),
    ("17. Route planner checks", run_route_planner_checks),
    ("18. Job query parsing checks", run_job_query_checks),
    ("19. Submit preview checks", run_submit_preview_checks),
    ("20. HPC env config checks", run_env_checks),
]

LIVE_HPC_CHECK_TITLE = "21. Live HPC workflow checks"


def main():
    parser = argparse.ArgumentParser(description="Run HPC Agent checks.")
    parser.add_argument(
        "--live-hpc",
        action="store_true",
        help="Also connect to HPC and submit a real Slurm test job.",
    )
    args = parser.parse_args()

    for title, check in CHECKS:
        print_section(title)
        check()

    print_section(LIVE_HPC_CHECK_TITLE)
    if args.live_hpc:
        run_live_hpc_checks()
    else:
        print("SKIPPED. Use --live-hpc to submit a real Slurm test job.")

    print_section("RESULT")
    print("All requested checks passed.")


if __name__ == "__main__":
    main()
