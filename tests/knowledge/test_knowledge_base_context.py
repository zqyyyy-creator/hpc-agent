from tests import _bootstrap  # noqa: F401

from modules.core.conversation_state import ConversationState
from modules.knowledge.knowledge_base import build_ask_llm_messages


def test_build_ask_llm_messages_includes_conversation_context():
    state = ConversationState()
    state.record_job("12345", "/remote/job/12345", {"kind": "slurm", "source": "submit"})
    state.record_pending_action("submit", {"script": "#!/bin/bash\nhostname\n"}, "提交 hostname 作业")
    state.remember_turn("user", "帮我提交 hostname")
    state.remember_turn("assistant", "请确认提交")

    docs = [
        {
            "source": "slurm.txt#chunk0",
            "score": 0.9,
            "content": "sbatch 用于提交 Slurm 作业。",
        }
    ]

    messages = build_ask_llm_messages("确认执行", docs, conversation_state=state)
    user_content = messages[1]["content"]

    assert "当前会话上下文" in user_content
    assert "待确认动作" in user_content
    assert "Job ID 12345" in user_content
    assert "用户: 帮我提交 hostname" in user_content
    assert "助手: 请确认提交" in user_content
    assert "sbatch 用于提交 Slurm 作业" in user_content


if __name__ == "__main__":
    test_build_ask_llm_messages_includes_conversation_context()
    print("All knowledge base context checks passed.")
