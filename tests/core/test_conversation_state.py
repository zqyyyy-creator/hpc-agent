from tests import _bootstrap  # noqa: F401

from modules.core.conversation_state import ConversationState


def test_record_job_creates_structured_recent_entry():
    state = ConversationState()
    state.record_job(
        "12345",
        "/remote/job/12345",
        {"kind": "slurm", "source": "submit", "command": "python train.py"},
    )

    job = state.recent_jobs[0]

    assert state.last_job_id == "12345"
    assert state.last_remote_workdir == "/remote/job/12345"
    assert job["job_id"] == "12345"
    assert job["kind"] == "slurm"
    assert job["source"] == "submit"
    assert job["metadata"]["command"] == "python train.py"
    assert "created_at" in job


def test_record_job_updates_existing_job_without_duplicate():
    state = ConversationState()
    state.record_job("12345", metadata={"kind": "slurm", "source": "submit"})
    state.record_job("67890", metadata={"kind": "test", "source": "test_run"})
    state.record_job("12345", metadata={"kind": "slurm", "source": "query"})

    assert [job["job_id"] for job in state.recent_jobs] == ["12345", "67890"]
    assert state.recent_jobs[0]["source"] == "query"


def test_resolve_latest_job_by_kind():
    state = ConversationState()
    state.record_job("10001", metadata={"kind": "slurm", "source": "submit"})
    state.record_job("20002", metadata={"kind": "vasp", "type": "vasp", "source": "submit"})
    state.record_job("30003", metadata={"kind": "test", "source": "test_run"})

    assert state.resolve_job_id("last") == "30003"
    assert state.resolve_job_id("刚才那个 VASP 作业") == "20002"
    assert state.resolve_job_id("最近那个测试作业") == "30003"
    assert state.resolve_job_id("last", kind="slurm") == "10001"


def test_resolve_ordinal_job_reference():
    state = ConversationState()
    state.record_job("10001", metadata={"kind": "slurm", "source": "submit"})
    state.record_job("20002", metadata={"kind": "slurm", "source": "submit"})
    state.record_job("30003", metadata={"kind": "slurm", "source": "submit"})

    assert state.resolve_job_id("第一个作业") == "30003"
    assert state.resolve_job_id("第二个作业") == "20002"
    assert state.resolve_job_id("第3个作业") == "10001"
    assert state.resolve_job_id("上一个") == "30003"


def test_resolve_by_source():
    state = ConversationState()
    state.record_job("10001", metadata={"kind": "slurm", "source": "submit"})
    state.record_job("20002", metadata={"kind": "slurm", "source": "query"})
    state.record_job("30003", metadata={"kind": "test", "source": "test_run"})

    assert state.resolve_job_id("last", source="submit") == "10001"
    assert state.resolve_job_id("last", source="test_run") == "30003"


def test_resolve_vasp_job_id_prefers_vasp_context():
    state = ConversationState()
    state.record_job("10001", metadata={"kind": "slurm", "source": "submit"})
    state.record_job("20002", metadata={"kind": "vasp", "type": "vasp", "source": "register"})
    state.record_job("30003", metadata={"kind": "test", "source": "test_run"})

    assert state.last_job_id == "30003"
    assert state.last_vasp_job_id == "20002"
    assert state.resolve_vasp_job_id("last") == "20002"


def test_pending_action_and_generic_confirmation_memory():
    state = ConversationState()
    state.record_pending_action(
        "submit",
        {"script": "#!/bin/bash\nhostname\n"},
        "提交作业预览",
    )
    state.remember_turn("user", "帮我提交 hostname")
    state.remember_turn("assistant", "请确认提交")

    assert state.pending_action["kind"] == "submit"
    assert state.is_confirmation("确认执行")
    assert state.is_confirmation("执行")
    assert state.is_cancellation("取消执行")
    assert "待确认动作" in state.context_summary()
    assert len(state.conversation_turns) == 2

    state.clear_pending_action("submit")
    assert state.pending_action is None


def test_answer_context_summary_includes_recent_turns_and_jobs():
    state = ConversationState()
    state.record_job("12345", "/remote/job/12345", {"kind": "slurm", "source": "submit"})
    state.record_pending_action("submit", {"script": "#!/bin/bash\nhostname\n"}, "提交 hostname 作业")
    state.remember_turn("user", "帮我提交 hostname")
    state.remember_turn("assistant", "请确认提交")

    summary = state.answer_context_summary()

    assert "待确认动作" in summary
    assert "Job ID 12345" in summary
    assert "最近对话" in summary
    assert "用户: 帮我提交 hostname" in summary
    assert "助手: 请确认提交" in summary


if __name__ == "__main__":
    test_record_job_creates_structured_recent_entry()
    test_record_job_updates_existing_job_without_duplicate()
    test_resolve_latest_job_by_kind()
    test_resolve_ordinal_job_reference()
    test_resolve_by_source()
    test_resolve_vasp_job_id_prefers_vasp_context()
    test_pending_action_and_generic_confirmation_memory()
    test_answer_context_summary_includes_recent_turns_and_jobs()
    print("All conversation state checks passed.")
