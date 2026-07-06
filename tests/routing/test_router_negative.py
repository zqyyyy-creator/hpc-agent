from tests import _bootstrap  # noqa: F401
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE
from modules.routing.router import analyze_intent, detect_intent, get_intent_risk, validate_keyword_catalogue
from modules.routing.router import analyze_plan
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


def test_cluster_partition_questions_route_to_rag():
    cases = {
        "amd_test能跑多久？": "rag_qa",
        "amd_256 的时间限制是多少": "rag_qa",
        "VASP 作业用哪个 partition": "rag_qa",
        "BSCC-A 上正式 VASP 作业应该提交到哪个 partition": "rag_qa",
        "BSCC-A 超算有哪些 partition 资源": "rag_qa",
        "all 分区能用吗": "rag_qa",
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


def test_file_named_test_py_routes_to_submit_not_test_generation():
    cases = {
        "帮我运行一个名字为 test.py 的文件": "submit_job",
        "帮我运行一个名字叫 test.py 的文件": "submit_job",
        "帮我运行 test.py": "submit_job",
        "帮我运行 test.py，不是生成测试文件": "submit_job",
        "帮我找一下 test.py, 然后运行": "submit_job",
        "test.py 帮我跑一下": "submit_job",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_preview_only_submit_routes_to_sbatch_generation():
    cases = {
        "不要提交，只生成脚本运行 python train.py": "generate_sbatch",
        "帮我提交 train.py，但先别运行": "generate_sbatch",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_vasp_script_generation_does_not_trigger_submission():
    cases = {
        "帮我生成一个 VASP 运行脚本": "generate_vasp_job",
        "给我一个 VASP sbatch 脚本": "generate_vasp_job",
        "帮我提交一个 VASP 结构优化任务，1 个节点 32 核": "submit_vasp_job",
    }

    for request, expected_intent in cases.items():
        assert detect_intent(request) == expected_intent


def test_plan_output_step_references_previous_submit():
    plan = analyze_plan("先运行 test.py，然后看输出")

    assert plan is not None
    assert [step.intent for step in plan.steps] == ["submit_job", "job_output"]
    assert plan.steps[1].route_text == "刚才那个作业看输出"
    assert not plan.steps[1].needs_clarification


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


def test_keyword_catalogue_has_no_duplicate_or_empty_entries():
    assert validate_keyword_catalogue() == []


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
    test_file_named_test_py_routes_to_submit_not_test_generation()
    test_preview_only_submit_routes_to_sbatch_generation()
    test_vasp_script_generation_does_not_trigger_submission()
    test_plan_output_step_references_previous_submit()
    test_ambiguous_requests_ask_for_clarification()
    test_route_decision_exposes_reason_keywords_and_risk()
    test_keyword_catalogue_has_no_duplicate_or_empty_entries()
    test_analyze_job_id_routes_to_vasp_when_registry_marks_job_as_vasp()
    test_analyze_last_job_routes_to_vasp_when_recent_context_marks_job_as_vasp()
    print("All router negative checks passed.")
