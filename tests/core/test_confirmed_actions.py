from tests import _bootstrap  # noqa: F401

from modules.core.confirmed_actions import execute_confirmed_action
from modules.core.conversation_state import ConversationState


def test_confirmed_slurm_submit_records_job():
    state = ConversationState()
    result = execute_confirmed_action(
        "submit",
        {
            "script": "#!/bin/bash\npython train.py\n",
            "uploaded_files": [{"name": "train.py", "content": b"print('ok')\n"}],
        },
        state=state,
        executors={
            "submit": lambda script, uploaded_files=None: {
                "success": True,
                "answer": "Submitted batch job 12345",
                "job_id": "12345",
                "raw": {"remote_workdir": "/remote/job/12345"},
            },
        },
    )

    assert result.success
    assert result.message == "Submitted batch job 12345"
    assert result.data["job_id"] == "12345"
    assert state.last_job_id == "12345"
    assert state.last_remote_workdir == "/remote/job/12345"


def test_confirmed_vasp_submit_records_vasp_job():
    state = ConversationState()
    result = execute_confirmed_action(
        "submit_vasp",
        {
            "script": "#!/bin/bash\nvasp_std\n",
            "source_text": "目录名 si_static_test",
        },
        state=state,
        executors={
            "submit_vasp": lambda script, source_text: {
                "success": True,
                "answer": "Submitted VASP job 22334",
                "job_id": "22334",
                "raw": {"remote_workdir": "/remote/vasp/22334"},
            },
        },
    )

    assert result.success
    assert result.data["submission_kind"] == "vasp"
    assert state.last_job_id == "22334"
    assert state.last_vasp_job_id == "22334"


def test_confirmed_cleanup_returns_answer_and_targets():
    targets = [{"path": "/remote/job/12345", "kind": "dir"}]
    result = execute_confirmed_action(
        "cleanup",
        {"kind": "job", "targets": targets},
        executors={
            "cleanup": lambda targets: f"cleaned {len(targets)} target",
        },
    )

    assert result.success
    assert result.message == "cleaned 1 target"
    assert result.data["targets"] == targets
    assert result.data["cleanup_kind"] == "job"


def test_unknown_confirmed_action_is_rejected():
    result = execute_confirmed_action("unknown", {})

    assert not result.success
    assert "不支持" in result.message


if __name__ == "__main__":
    test_confirmed_slurm_submit_records_job()
    test_confirmed_vasp_submit_records_vasp_job()
    test_confirmed_cleanup_returns_answer_and_targets()
    test_unknown_confirmed_action_is_rejected()
    print("All confirmed action checks passed.")
