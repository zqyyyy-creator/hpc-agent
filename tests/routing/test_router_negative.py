from tests import _bootstrap  # noqa: F401
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE
from modules.routing.router import analyze_intent, detect_intent, get_intent_risk
from modules.slurm import job_registry


def test_howto_questions_do_not_trigger_actions():
    cases = {
        "怎么提交作业": "rag_qa",
        "GPU 作业怎么申请资源": "rag_qa",
        "提交作业怎么申请资源，需要多少核": "rag_qa",
        "资源怎么填，申请多少核，多少内存": "rag_qa",
        "如何写 sbatch 脚本": "rag_qa",
        "VASP 是什么": "rag_qa",
        "INCAR 和 POSCAR 有什么区别": "rag_qa",
        "删除本地文件怎么恢复": "rag_qa",
        "怎么删除作业": "rag_qa",
        "如何查看作业状态": "rag_qa",
        "VASP 输出文件有哪些": "rag_qa",
        "帮我写一个介绍 VASP 的脚本": "rag_qa",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_resource_questions_beat_submit_phrases():
    cases = {
        "帮我看看需要多少核再提交": "suggest_params",
        "跑 VASP 结构优化需要多少核": "suggest_params",
        "我想提交作业，但还不知道资源怎么填": "rag_qa",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_unrelated_delete_or_local_cleanup_is_not_remote_cleanup():
    cases = {
        "删除本地临时文件": "rag_qa",
        "清理 Python 缓存要怎么做": "rag_qa",
        "remove local cache files": "rag_qa",
        "不要清理远端文件，只告诉我怎么清理": "rag_qa",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_negated_actions_change_or_block_intent():
    cases = {
        "不要提交，只生成脚本运行 python train.py": "generate_sbatch",
        "不是 VASP，是普通 Python 作业，运行 python train.py": "submit_job",
        "不要清理远端文件，只告诉我怎么清理": "rag_qa",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_ambiguous_requests_ask_for_clarification():
    cases = {
        "帮我跑一下": "clarify",
        "提交这个": "clarify",
        "看一下结果": "clarify",
    }

    for request, expected_intent in cases.items():
        decision = analyze_intent(request)
        assert decision.intent == expected_intent
        assert decision.needs_clarification
        assert decision.risk == "clarify_required"
        assert decision.clarification


def test_route_decision_exposes_reason_keywords_and_risk():
    decision = analyze_intent("跑 VASP 结构优化需要多少核")

    assert decision.intent == "suggest_params"
    assert decision.risk == "none"
    assert decision.reason == "keyword_rule_matched"
    assert decision.matched_keywords
    assert get_intent_risk("cleanup_remote_job") == "destructive_confirm_required"


def test_analyze_job_id_routes_to_vasp_when_registry_marks_job_as_vasp():
    original_registry_path = job_registry.REGISTRY_PATH
    temp_dir = TemporaryDirectory()

    try:
        job_registry.REGISTRY_PATH = Path(temp_dir.name) / "job_registry.json"
        job_registry.register_job("11836171", {"type": "vasp", "job_id": "11836171"})

        assert detect_intent("分析11836171") == "analyze_vasp_job"
    finally:
        job_registry.REGISTRY_PATH = original_registry_path
        temp_dir.cleanup()


def test_analyze_last_job_routes_to_vasp_when_recent_context_marks_job_as_vasp():
    original_recent_jobs = list(GLOBAL_CONVERSATION_STATE.recent_jobs)
    original_last_job_id = GLOBAL_CONVERSATION_STATE.last_job_id
    original_last_vasp_job_id = GLOBAL_CONVERSATION_STATE.last_vasp_job_id

    try:
        GLOBAL_CONVERSATION_STATE.recent_jobs = []
        GLOBAL_CONVERSATION_STATE.last_job_id = None
        GLOBAL_CONVERSATION_STATE.last_vasp_job_id = None
        GLOBAL_CONVERSATION_STATE.record_job("11836172", metadata={"type": "vasp"})

        assert detect_intent("分析刚才那个作业") == "analyze_vasp_job"
    finally:
        GLOBAL_CONVERSATION_STATE.recent_jobs = original_recent_jobs
        GLOBAL_CONVERSATION_STATE.last_job_id = original_last_job_id
        GLOBAL_CONVERSATION_STATE.last_vasp_job_id = original_last_vasp_job_id


if __name__ == "__main__":
    test_howto_questions_do_not_trigger_actions()
    test_resource_questions_beat_submit_phrases()
    test_unrelated_delete_or_local_cleanup_is_not_remote_cleanup()
    test_negated_actions_change_or_block_intent()
    test_ambiguous_requests_ask_for_clarification()
    test_route_decision_exposes_reason_keywords_and_risk()
    test_analyze_job_id_routes_to_vasp_when_registry_marks_job_as_vasp()
    test_analyze_last_job_routes_to_vasp_when_recent_context_marks_job_as_vasp()
    print("All router negative checks passed.")
