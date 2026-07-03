from tests import _bootstrap  # noqa: F401

from modules.core import agent_runtime
from modules.skills import skill_executor
from modules.core.agent_runtime import (
    can_answer_intent,
    can_preview_cleanup_intent,
    can_preview_submit_intent,
    execute_answer_intent,
    execute_cleanup_preview,
    execute_submit_preview,
)
from modules.core.conversation_state import ConversationState


class DummyDiagnoser:
    def diagnose(self, text):
        return [{"kind": "dummy", "text": text}]

    def format_results(self, results):
        return f"diagnosed: {results[0]['text']}"


def test_can_answer_intent_marks_only_answer_intents():
    assert can_answer_intent("shortcut_help")
    assert can_answer_intent("project_doctor")
    assert can_answer_intent("generate_sbatch")
    assert can_answer_intent("current_config")
    assert can_answer_intent("check_hpc_config")
    assert can_answer_intent("troubleshoot_job")
    assert can_answer_intent("prepare_error_case")
    assert can_answer_intent("rag_qa")
    assert can_answer_intent("job_status")
    assert can_answer_intent("sync_vasp_output")
    assert not can_answer_intent("submit_job")
    assert not can_answer_intent("cleanup_remote_job")


def test_execute_shortcut_help_returns_static_help():
    result = execute_answer_intent(
        "/help vasp",
        "shortcut_help",
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=None,
    )

    assert result.handled
    assert result.intent == "shortcut_help"
    assert "/vasp gen <name>" in result.answer
    assert "POTCAR" in result.answer


def test_execute_registered_skill_intent_exposes_skill_metadata():
    result = execute_answer_intent(
        "生成一个 sbatch 脚本运行 python train.py",
        "generate_sbatch",
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=None,
    )

    assert result.handled
    assert result.data["skill"]["name"] == "generate-sbatch"
    assert result.data["skill"]["type"] == "tool"
    assert result.data["skill"]["handler"] == "modules.slurm.slurm_assistant.generate_sbatch_script"
    assert result.data["runtime"]["adapter"] == "question_to_text"
    assert result.data["runtime"]["handler"] == "modules.slurm.slurm_assistant.generate_sbatch_script"


def test_execute_registered_skill_falls_back_to_rag_when_handler_fails():
    original_execute_skill = agent_runtime.execute_skill
    original_ask_llm = agent_runtime.ask_llm

    def failing_execute_skill(*args, **kwargs):
        raise RuntimeError("boom")

    try:
        agent_runtime.execute_skill = failing_execute_skill
        agent_runtime.ask_llm = lambda question, docs, conversation_state=None: "fallback answer"
        result = execute_answer_intent(
            "amd_test 能跑多久",
            "generate_sbatch",
            documents=["amd_test 最大运行时间 30 分钟"],
            sources=["cluster_sinfo_bscc_a.txt#chunk0"],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        agent_runtime.execute_skill = original_execute_skill
        agent_runtime.ask_llm = original_ask_llm

    assert result.handled
    assert result.success
    assert result.data["skill_fallback"]
    assert result.data["failed_skill"]["name"] == "generate-sbatch"
    assert "已切换到知识库回答" in result.answer
    assert "fallback answer" in result.answer


def test_execute_tool_dispatch_skill_uses_dispatch_adapter():
    original_dispatch = skill_executor.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "job output text"
        data = {"job_id": "12345"}

    try:
        skill_executor.dispatch_tool_request = lambda *args, **kwargs: FakeDispatchResult()
        result = execute_answer_intent(
            "读取 12345 的输出",
            "job_output",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=ConversationState(),
        )
    finally:
        skill_executor.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.success
    assert result.answer == "job output text"
    assert result.data["runtime"]["adapter"] == "tool_dispatch"
    assert result.data["skill"]["name"] == "inspect-job"
    assert result.data["live_log"] == "job output text"


def test_execute_project_doctor_intent_formats_health_report():
    original_run_project_doctor = agent_runtime.run_project_doctor

    try:
        agent_runtime.run_project_doctor = lambda **kwargs: {
            "success": True,
            "sections": {
                "project_paths": {"success": True, "checks": [{"ok": True, "label": ".env", "detail": "存在"}]},
                "hpc_environment": {"success": True, "checks": [{"ok": True, "label": "HPC_HOST", "detail": "set"}]},
                "rag_documents": {"success": True, "checks": [{"ok": True, "label": "RAG chunks", "detail": "10 chunks"}]},
                "skill_registry": {"success": True, "checks": [{"ok": True, "label": "Skill count", "detail": "8 skills"}]},
                "local_resources": {"success": True, "checks": [{"ok": True, "label": "CPU", "detail": "4 logical cores"}]},
            },
        }
        result = execute_answer_intent(
            "/doctor",
            "project_doctor",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        agent_runtime.run_project_doctor = original_run_project_doctor

    assert result.handled
    assert result.success
    assert "HPC Agent 总体体检" in result.answer
    assert "RAG 文档" in result.answer


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


def test_execute_prepare_error_case_returns_pending_action():
    state = ConversationState()
    result = execute_answer_intent(
        "把这个错误整理成案例：CustomRuntimeError: example failed",
        "prepare_error_case",
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=state,
    )

    assert result.handled
    assert result.success
    assert "案例草稿" in result.answer
    assert result.data["pending_action"]["kind"] == "add_error_case"
    assert result.data["pending_action"]["payload"]["case"]["patterns"]


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
    original_dispatch = skill_executor.dispatch_tool_request

    class FakeDispatchResult:
        success = True
        message = "output text"
        data = {"job_id": "12345"}

    try:
        skill_executor.dispatch_tool_request = lambda *args, **kwargs: FakeDispatchResult()
        result = execute_answer_intent(
            "看 12345 的输出",
            "job_output",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=None,
        )
    finally:
        skill_executor.dispatch_tool_request = original_dispatch

    assert result.handled
    assert result.success
    assert result.answer == "output text"
    assert result.data["job_id"] == "12345"
    assert result.data["live_log"] == "output text"
    assert result.data["runtime"]["adapter"] == "tool_dispatch"


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


def test_execute_vasp_input_existing_files_returns_overwrite_pending_action():
    handler_module = skill_executor._import_dotted_path(
        "modules.vasp.vasp_input_generator.generate_vasp_inputs_from_potcar_request"
    ).__module__
    import importlib

    module = importlib.import_module(handler_module)
    original = module.generate_vasp_inputs_from_potcar_request

    try:
        module.generate_vasp_inputs_from_potcar_request = lambda question: {
            "success": False,
            "message": "没有写入文件，因为作业目录中已经存在 VASP 配置文件。",
            "job_dir": "/tmp/MgO_test",
            "existing_files": ["INCAR", "KPOINTS", "POSCAR"],
        }
        result = execute_answer_intent(
            "帮我生成我的vasp作业MgO_test的配置文件",
            "generate_vasp_inputs",
            documents=[],
            sources=[],
            diagnoser=DummyDiagnoser(),
            state=ConversationState(),
        )
    finally:
        module.generate_vasp_inputs_from_potcar_request = original

    assert result.handled
    assert not result.success
    assert result.data["runtime"]["adapter"] == "structured_result"
    assert result.data["skill"]["name"] == "generate-vasp-inputs"
    assert result.data["pending_action"]["kind"] == "generate_vasp_inputs_overwrite"
    assert result.data["pending_action"]["payload"]["job_dir"] == "/tmp/MgO_test"
    assert "确认覆盖" in result.answer


if __name__ == "__main__":
    test_can_answer_intent_marks_only_answer_intents()
    test_execute_registered_skill_intent_exposes_skill_metadata()
    test_execute_tool_dispatch_skill_uses_dispatch_adapter()
    test_can_preview_cleanup_intent_marks_cleanup_intents()
    test_can_preview_submit_intent_marks_submit_intents()
    test_execute_clarify_intent_does_not_need_llm()
    test_execute_diagnose_intent_uses_injected_diagnoser()
    test_execute_prepare_error_case_returns_pending_action()
    test_execute_diagnose_job_intent_uses_job_diagnosis()
    test_execute_current_config_intent_reports_models()
    test_execute_job_output_returns_job_id_and_live_log()
    test_execute_cleanup_preview_returns_pending_payload()
    test_execute_submit_preview_returns_pending_submission()
    test_execute_hpc_submission_test_returns_pending_submission()
    test_execute_vasp_submit_preview_keeps_auto_analyze()
    test_execute_vasp_input_existing_files_returns_overwrite_pending_action()
    print("All agent runtime checks passed.")
