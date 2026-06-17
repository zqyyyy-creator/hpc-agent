from tests import _bootstrap  # noqa: F401

from modules.core import agent_runtime
from modules.core.agent_runtime import (
    can_answer_intent,
    can_preview_cleanup_intent,
    can_preview_submit_intent,
    execute_answer_intent,
    execute_cleanup_preview,
    execute_submit_preview,
)


class DummyDiagnoser:
    def diagnose(self, text):
        return [{"kind": "dummy", "text": text}]

    def format_results(self, results):
        return f"diagnosed: {results[0]['text']}"


def test_can_answer_intent_marks_only_answer_intents():
    assert can_answer_intent("generate_sbatch")
    assert can_answer_intent("current_config")
    assert can_answer_intent("check_hpc_config")
    assert can_answer_intent("troubleshoot_job")
    assert can_answer_intent("rag_qa")
    assert can_answer_intent("job_status")
    assert can_answer_intent("sync_vasp_output")
    assert not can_answer_intent("submit_job")
    assert not can_answer_intent("cleanup_remote_job")


def test_can_preview_cleanup_intent_marks_cleanup_intents():
    assert can_preview_cleanup_intent("cleanup_remote_job")
    assert can_preview_cleanup_intent("cleanup_all_remote_vasp_jobs")
    assert not can_preview_cleanup_intent("submit_job")


def test_can_preview_submit_intent_marks_submit_intents():
    assert can_preview_submit_intent("submit_job")
    assert can_preview_submit_intent("submit_vasp_job")
    assert can_preview_submit_intent("test_hpc_submission")
    assert not can_preview_submit_intent("cleanup_remote_job")


def test_execute_clarify_intent_does_not_need_llm():
    result = execute_answer_intent(
        "帮我跑",
        "clarify",
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=None,
    )

    assert result.handled
    assert result.intent == "clarify"
    assert "补充" in result.answer or "哪个" in result.answer


def test_execute_diagnose_intent_uses_injected_diagnoser():
    result = execute_answer_intent(
        "CUDA out of memory",
        "diagnose_error",
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=None,
    )

    assert result.handled
    assert result.answer == "diagnosed: CUDA out of memory"


def test_execute_diagnose_job_intent_uses_job_diagnosis():
    original = agent_runtime.diagnose_job_request

    try:
        agent_runtime.diagnose_job_request = lambda question, state=None: f"diagnose job from {question}"
        result = execute_answer_intent(
            "诊断作业 12345",
            "diagnose_job",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        agent_runtime.diagnose_job_request = original

    assert result.handled
    assert result.answer == "diagnose job from 诊断作业 12345"


def test_execute_current_config_intent_reports_models():
    result = execute_answer_intent(
        "查看当前模型",
        "current_config",
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=None,
    )

    assert result.handled
    assert "Agent 主体模型" in result.answer
    assert "Claude Code VASP 报告模型" in result.answer
    assert "API Key: <已配置>" in result.answer or "API Key: <未配置>" in result.answer


def test_execute_archive_preview_returns_pending_action():
    original = agent_runtime.build_archive_job_records_preview

    try:
        agent_runtime.build_archive_job_records_preview = lambda question: {
            "success": True,
            "message": "preview",
            "requires_confirmation": True,
            "keep_count": 2,
            "keep_job_ids": ["30003", "20002"],
            "archive_job_ids": ["10001"],
        }
        result = execute_answer_intent(
            "预览归档本地作业记录，只保留最近 2 个",
            "preview_archive_job_records",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        agent_runtime.build_archive_job_records_preview = original

    assert result.handled
    assert result.answer == "preview"
    assert result.data["pending_action"]["kind"] == "archive_job_records"
    assert result.data["pending_action"]["payload"]["archive_job_ids"] == ["10001"]


def test_execute_restore_preview_returns_pending_action():
    original = agent_runtime.build_restore_job_records_preview

    try:
        agent_runtime.build_restore_job_records_preview = lambda question: {
            "success": True,
            "message": "restore preview",
            "requires_confirmation": True,
            "archive_path": "/tmp/archive.json",
            "restore_job_ids": ["10001"],
            "skipped_job_ids": [],
        }
        result = execute_answer_intent(
            "预览恢复最近一次本地作业记录归档",
            "preview_restore_job_records",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        agent_runtime.build_restore_job_records_preview = original

    assert result.handled
    assert result.answer == "restore preview"
    assert result.data["pending_action"]["kind"] == "restore_job_records"
    assert result.data["pending_action"]["payload"]["restore_job_ids"] == ["10001"]


def test_execute_job_output_returns_job_id_and_live_log():
    original_dispatch = agent_runtime.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "output text"
        data = {"job_id": "12345"}

    try:
        agent_runtime.dispatch_tool_request = lambda *args, **kwargs: FakeDispatchResult()
        result = execute_answer_intent(
            "看 12345 的输出",
            "job_output",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        agent_runtime.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.success
    assert result.answer == "output text"
    assert result.data["job_id"] == "12345"
    assert result.data["live_log"] == "output text"


def test_execute_cleanup_preview_returns_pending_payload():
    original_dispatch = agent_runtime.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "cleanup preview"
        data = {
            "ready": True,
            "targets": [{"path": "/remote/job/12345"}],
            "job_id": "12345",
        }

    try:
        agent_runtime.dispatch_tool_request = lambda *args, **kwargs: FakeDispatchResult()
        result = execute_cleanup_preview(
            "清理远端作业 12345 的文件",
            "cleanup_remote_job",
            state=None,
        )
    finally:
        agent_runtime.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.success
    assert result.answer == "cleanup preview"
    assert result.data["requires_confirmation"]
    assert result.data["pending_cleanup"] == {
        "kind": "job",
        "targets": [{"path": "/remote/job/12345"}],
        "job_id": "12345",
    }


def test_execute_submit_preview_returns_pending_submission():
    original_dispatch = agent_runtime.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "submit preview"
        data = {
            "prepared": {
                "ready": True,
                "message": "submit preview",
                "script": "#!/bin/bash\nhostname\n",
            },
            "script": "#!/bin/bash\nhostname\n",
            "uploaded_files": [{"name": "job.sh", "content": b"hostname\n"}],
            "source_text": "提交 job.sh",
        }

    try:
        agent_runtime.dispatch_tool_request = lambda *args, **kwargs: FakeDispatchResult()
        result = execute_submit_preview(
            "提交 job.sh",
            "submit_job",
            state=None,
            uploaded_files=[{"name": "job.sh", "content": b"hostname\n"}],
        )
    finally:
        agent_runtime.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.success
    assert result.data["requires_confirmation"]
    assert result.data["pending_submission"]["kind"] == "slurm"
    assert result.data["pending_submission"]["script"].startswith("#!/bin/bash")


def test_execute_hpc_submission_test_returns_pending_submission():
    original_dispatch = agent_runtime.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "smoke test preview"
        data = {
            "prepared": {
                "ready": True,
                "message": "smoke test preview",
                "script": "#!/bin/bash\nhostname\n",
            },
            "script": "#!/bin/bash\nhostname\n",
            "uploaded_files": [],
            "source_text": "hostname smoke test",
        }

    calls = []

    try:
        def fake_dispatch(*args, **kwargs):
            calls.append((args, kwargs))
            return FakeDispatchResult()

        agent_runtime.dispatch_tool_request = fake_dispatch
        result = execute_submit_preview(
            "一键测试超算提交流程",
            "test_hpc_submission",
            state=None,
        )
    finally:
        agent_runtime.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.success
    assert calls[0][0][1] == "submit_job"
    assert calls[0][0][0] == "一键测试超算提交流程"
    assert result.data["requires_confirmation"]
    assert result.data["pending_submission"]["kind"] == "slurm"
    assert "最小 hostname 作业" in result.answer


def test_execute_vasp_submit_preview_keeps_auto_analyze():
    original_dispatch = agent_runtime.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "vasp preview"
        data = {
            "prepared": {
                "ready": True,
                "message": "vasp preview",
                "script": "#!/bin/bash\nvasp_std\n",
            },
            "script": "#!/bin/bash\nvasp_std\n",
            "uploaded_files": [],
            "source_text": "提交 VASP 并分析",
        }

    try:
        agent_runtime.dispatch_tool_request = lambda *args, **kwargs: FakeDispatchResult()
        result = execute_submit_preview(
            "提交 VASP 并分析",
            "submit_vasp_job",
            state=None,
            auto_analyze=True,
        )
    finally:
        agent_runtime.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.data["pending_submission"]["kind"] == "vasp"
    assert result.data["pending_submission"]["auto_analyze"]
    assert "自动进入长流程" in result.answer


if __name__ == "__main__":
    test_can_answer_intent_marks_only_answer_intents()
    test_can_preview_cleanup_intent_marks_cleanup_intents()
    test_can_preview_submit_intent_marks_submit_intents()
    test_execute_clarify_intent_does_not_need_llm()
    test_execute_diagnose_intent_uses_injected_diagnoser()
    test_execute_diagnose_job_intent_uses_job_diagnosis()
    test_execute_current_config_intent_reports_models()
    test_execute_job_output_returns_job_id_and_live_log()
    test_execute_cleanup_preview_returns_pending_payload()
    test_execute_submit_preview_returns_pending_submission()
    test_execute_hpc_submission_test_returns_pending_submission()
    test_execute_vasp_submit_preview_keeps_auto_analyze()
    print("All agent runtime checks passed.")
