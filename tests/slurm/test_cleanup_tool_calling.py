from tests import _bootstrap  # noqa: F401

from modules.routing.router import detect_intent
from modules.slurm.job_query import (
    execute_cleanup_prepare_tool_call,
    handle_cleanup_prepare_request,
    make_cleanup_tool_call,
    validate_cleanup_tool_call,
)


def _prepared(kind="job", ready=True):
    return {
        "ready": ready,
        "kind": kind,
        "job_id": "12345" if kind == "job" else None,
        "selector": "si_static_test" if kind == "vasp_job" else None,
        "scope": "both",
        "targets": [{"kind": "file", "path": "job.sh", "remote_workdir": "/remote/job"}],
        "message": "cleanup preview",
    }


def test_make_cleanup_tool_call_for_regular_job():
    call = make_cleanup_tool_call("清理远端作业 12345 的文件", "cleanup_remote_job")

    assert call.tool == "prepare_cleanup_remote_job"
    assert call.arguments["job_id"] == "12345"
    assert call.needs_confirmation


def test_cleanup_regular_job_prepare_result():
    result = handle_cleanup_prepare_request(
        "清理远端作业 12345 的文件",
        "cleanup_remote_job",
        prepare_funcs={
            "prepare_cleanup_remote_job": lambda call: _prepared("job"),
        },
    )

    assert result.success
    assert result.data["ready"]
    assert result.data["required_confirmation"] == "确认清理"
    assert result.data["targets"][0]["path"] == "job.sh"


def test_cleanup_all_regular_jobs_requires_strong_confirmation():
    result = handle_cleanup_prepare_request(
        "清理远端 hpc-agent-jobs 下所有作业文件",
        "cleanup_all_remote_jobs",
        prepare_funcs={
            "prepare_cleanup_all_remote_jobs": lambda call: _prepared("all"),
        },
    )

    assert result.success
    assert result.data["required_confirmation"] == "确认清理全部"


def test_cleanup_vasp_job_scope_and_selector():
    call = make_cleanup_tool_call(
        "删除远端 VASP 作业 si_static_test 的 output 目录",
        "cleanup_remote_vasp_job",
    )
    validated = validate_cleanup_tool_call(call)

    assert validated.tool == "prepare_cleanup_remote_vasp_job"
    assert validated.arguments["selector"] == "si_static_test"
    assert validated.arguments["scope"] == "output"


def test_cleanup_all_vasp_jobs_requires_strong_confirmation():
    result = handle_cleanup_prepare_request(
        "清空远端 VASP input 下所有作业",
        "cleanup_all_remote_vasp_jobs",
        prepare_funcs={
            "prepare_cleanup_all_remote_vasp_jobs": lambda call: _prepared("vasp_all"),
        },
    )

    assert result.success
    assert result.data["required_confirmation"] == "确认清理全部"
    assert result.tool_call.arguments["scope"] == "input"


def test_generic_vasp_directory_cleanup_routes_to_all_vasp_cleanup():
    assert detect_intent("清理远端vasp作业目录") == "cleanup_all_remote_vasp_jobs"


def test_cleanup_missing_job_id_asks_for_clarification():
    result = execute_cleanup_prepare_tool_call(
        {"tool": "prepare_cleanup_remote_job", "arguments": {"job_id": None}},
    )

    assert not result.success
    assert "Job ID" in result.message


if __name__ == "__main__":
    test_make_cleanup_tool_call_for_regular_job()
    test_cleanup_regular_job_prepare_result()
    test_cleanup_all_regular_jobs_requires_strong_confirmation()
    test_cleanup_vasp_job_scope_and_selector()
    test_cleanup_all_vasp_jobs_requires_strong_confirmation()
    test_generic_vasp_directory_cleanup_routes_to_all_vasp_cleanup()
    test_cleanup_missing_job_id_asks_for_clarification()
    print("All cleanup tool calling checks passed.")
