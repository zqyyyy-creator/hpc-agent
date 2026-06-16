from tests import _bootstrap  # noqa: F401
import os
import tempfile
from pathlib import Path

from modules.core.conversation_state import ConversationState
from modules.core.tool_calling import ToolCall, ToolResult
from modules.routing.tool_dispatcher import can_dispatch_intent, dispatch_classified_intent, dispatch_tool_request


def test_dispatcher_ignores_non_tool_intent():
    result = dispatch_tool_request("资源怎么填", "suggest_params")

    assert not result.handled
    assert result.intent == "suggest_params"


def test_dispatcher_handles_slurm_submit_preview():
    result = dispatch_tool_request(
        "帮我提交 python train.py，4 核 10 分钟",
        "submit_job",
        uploaded_files=[{"name": "train.py", "content": b"print('ok')\n"}],
        handlers={
            "submit_job": lambda text: {
                "ready": True,
                "message": "submit preview",
                "script": "#!/bin/bash\npython train.py\n",
            },
        },
    )

    assert result.handled
    assert result.success
    assert result.message == "submit preview"
    assert result.data["ready"]
    assert result.data["submission_kind"] == "slurm"
    assert result.data["script"].startswith("#!/bin/bash")
    assert result.data["uploaded_files"][0]["name"] == "train.py"


def test_dispatcher_handles_vasp_submit_preview():
    result = dispatch_tool_request(
        "帮我提交一个 VASP 静态计算任务",
        "submit_vasp_job",
        source_text="目录名 si_static_test",
        handlers={
            "submit_vasp_job": lambda text: {
                "ready": True,
                "message": "vasp preview",
                "script": "#!/bin/bash\nvasp_std\n",
                "local_jobs_dir": "/local/vasp",
                "remote_input_dir": "/remote/input",
                "remote_output_dir": "/remote/output",
            },
        },
    )

    assert result.handled
    assert result.success
    assert result.data["submission_kind"] == "vasp"
    assert result.data["source_text"] == "目录名 si_static_test"
    assert result.data["remote_output_dir"] == "/remote/output"


def test_dispatcher_handles_test_file_request_with_injected_handler():
    result = dispatch_tool_request(
        "生成一个 sleep 60 的测试作业脚本",
        handlers={
            "generate_test_file": lambda text: f"generated from {text}",
        },
    )

    assert result.handled
    assert result.success
    assert result.intent == "generate_test_file"
    assert result.message == "generated from 生成一个 sleep 60 的测试作业脚本"


def test_dispatcher_handles_job_query_with_state():
    state = ConversationState()
    state.record_job("12345")
    result = dispatch_tool_request(
        "查看刚才那个作业",
        "job_status",
        state=state,
        handlers={
            "job_query": lambda text, intent, state: ToolResult(
                success=True,
                message=f"{intent}:{state.last_job_id}",
                data={"job_id": state.last_job_id},
                tool_call=ToolCall("query_job_status", {"job_id": state.last_job_id}),
            ),
        },
    )

    assert result.handled
    assert result.success
    assert result.message == "job_status:12345"
    assert result.data["job_id"] == "12345"


def test_dispatcher_handles_cleanup_preview():
    result = dispatch_tool_request(
        "清理远端作业 12345 的文件",
        "cleanup_remote_job",
        handlers={
            "cleanup": lambda text, intent: ToolResult(
                success=True,
                message="cleanup preview",
                data={"ready": True, "targets": [{"path": "job.sh"}]},
                tool_call=ToolCall("prepare_cleanup_remote_job", {"job_id": "12345"}),
            ),
        },
    )

    assert result.handled
    assert result.success
    assert result.data["ready"]
    assert result.data["targets"][0]["path"] == "job.sh"


def test_dispatcher_handles_vasp_postprocess():
    state = ConversationState()
    result = dispatch_tool_request(
        "同步 VASP 作业 11817144 的输出",
        "sync_vasp_output",
        state=state,
        handlers={
            "vasp_postprocess": lambda text, intent, state: ToolResult(
                success=True,
                message="synced",
                data={"job_id": "11817144"},
                tool_call=ToolCall("sync_vasp_output", {"job_id": "11817144"}),
            ),
        },
    )

    assert result.handled
    assert result.success
    assert result.data["job_id"] == "11817144"


def test_llm_classified_test_file_preserves_structured_slots():
    original = os.environ.get("HPC_LOCAL_WORKDIR")

    try:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            os.environ["HPC_LOCAL_WORKDIR"] = tmpdir
            result = dispatch_classified_intent(
                ToolCall(
                    "generate_test_file",
                    {
                        "test_kind": "sleep",
                        "seconds": 90,
                        "file_name": "wait.py",
                    },
                    source="llm",
                ),
                "generate_test_file",
            )

            assert (Path(tmpdir) / "wait.py").is_file()
    finally:
        if original is None:
            os.environ.pop("HPC_LOCAL_WORKDIR", None)
        else:
            os.environ["HPC_LOCAL_WORKDIR"] = original

    assert result.handled
    assert result.success
    assert "sleep 90" in result.message
    assert "wait.py" in result.message
    assert result.tool_result.tool_call.arguments["spec"]["command"] == "sleep 90"


def test_llm_classified_vasp_cleanup_preserves_selector_and_scope():
    result = dispatch_classified_intent(
        ToolCall(
            "prepare_cleanup_remote_vasp_job",
            {
                "selector": "si_static_test",
                "cleanup_scope": "output",
                "is_vasp": True,
            },
            source="llm",
            needs_confirmation=True,
        ),
        "cleanup_remote_vasp_job",
        handlers={
            "cleanup": lambda text, intent: ToolResult(
                success=True,
                message=text,
                data={"intent": intent},
                tool_call=ToolCall("prepare_cleanup_remote_vasp_job", {"original_text": text}),
            ),
        },
    )

    assert result.handled
    assert result.success
    assert "si_static_test" in result.message
    assert "output" in result.message


def test_can_dispatch_intent_marks_tool_intents():
    assert can_dispatch_intent("generate_test_file")
    assert can_dispatch_intent("sync_vasp_output")
    assert can_dispatch_intent("submit_job")
    assert can_dispatch_intent("submit_vasp_job")
    assert not can_dispatch_intent("suggest_params")


if __name__ == "__main__":
    test_dispatcher_ignores_non_tool_intent()
    test_dispatcher_handles_slurm_submit_preview()
    test_dispatcher_handles_vasp_submit_preview()
    test_dispatcher_handles_test_file_request_with_injected_handler()
    test_dispatcher_handles_job_query_with_state()
    test_dispatcher_handles_cleanup_preview()
    test_dispatcher_handles_vasp_postprocess()
    test_llm_classified_test_file_preserves_structured_slots()
    test_llm_classified_vasp_cleanup_preserves_selector_and_scope()
    test_can_dispatch_intent_marks_tool_intents()
    print("All tool dispatcher checks passed.")
