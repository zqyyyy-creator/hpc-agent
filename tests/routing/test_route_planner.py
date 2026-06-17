from tests import _bootstrap  # noqa: F401

from modules.core.conversation_state import ConversationState
from modules.routing.router import (
    analyze_plan,
    can_execute_plan_all,
    detect_intent,
    format_route_plan,
    parse_plan_step_selection,
    serialize_route_plan,
)


def test_conditional_vasp_workflow_becomes_plan():
    request = "先看看上次的 VASP 跑完没，跑完了帮我同步结果并生成报告"
    plan = analyze_plan(request)

    assert plan is not None
    assert plan.is_conditional
    assert [step.intent for step in plan.steps] == [
        "job_status",
        "sync_vasp_output",
        "generate_vasp_report",
    ]
    assert plan.steps[1].condition
    assert plan.risk == "read_only"


def test_sequential_regular_workflow_becomes_plan():
    request = "先查看刚才那个作业的状态，然后看它的输出，最后看错误日志"
    plan = analyze_plan(request)

    assert plan is not None
    assert [step.intent for step in plan.steps] == [
        "job_status",
        "job_output",
        "job_error",
    ]


def test_single_vasp_submit_and_analyze_phrase_stays_single_intent():
    request = "提交并分析 VASP 作业，路径为 /tmp/hpc-agent-test/vasp-jobs-input/si_static_test"

    assert analyze_plan(request) is None
    assert detect_intent(request) == "submit_vasp_job"


def test_plan_formatter_mentions_no_auto_execution():
    plan = analyze_plan("先查看刚才那个作业的状态，然后看它的输出")

    assert plan is not None
    formatted = format_route_plan(plan)
    assert "多步骤请求" in formatted
    assert "确认1" in formatted


def test_confirm_step_resolves_to_saved_route_text():
    plan = analyze_plan("先看看上次的 VASP 跑完没，跑完了帮我同步结果并生成报告")
    state = ConversationState()
    state.record_route_plan(serialize_route_plan(plan))

    selected = parse_plan_step_selection("确认1")
    step = state.get_route_plan_step(selected)

    assert selected == 1
    assert step["intent"] == "job_status"
    assert step["route_text"] == "看看上次的 VASP 跑完没"
    assert detect_intent(step["route_text"]) == "job_status"


def test_confirm_second_step_keeps_vasp_context():
    plan = analyze_plan("先看看上次的 VASP 跑完没，跑完了帮我同步结果并生成报告")
    state = ConversationState()
    state.record_route_plan(serialize_route_plan(plan))

    selected = parse_plan_step_selection("确认2")
    step = state.get_route_plan_step(selected)

    assert selected == 2
    assert step["text"] == "帮我同步结果"
    assert step["route_text"] == "上次 VASP 作业 帮我同步结果"
    assert detect_intent(step["route_text"]) == "sync_vasp_output"


def test_execute_all_selection_is_supported_for_safe_plan():
    plan = analyze_plan("先查看刚才那个作业的状态，然后看它的输出，最后看错误日志")
    state = ConversationState()
    state.record_route_plan(serialize_route_plan(plan))

    assert parse_plan_step_selection("全部执行") == "all"
    assert parse_plan_step_selection("执行全部") == "all"
    assert can_execute_plan_all(state.pending_route_plan)


def test_execute_all_rejects_confirm_required_plan():
    plan = analyze_plan("先生成一个 sbatch 脚本运行 python train.py，然后提交 /tmp/train.py，4核")
    state = ConversationState()
    state.record_route_plan(serialize_route_plan(plan))

    assert plan is not None
    assert not can_execute_plan_all(state.pending_route_plan)


if __name__ == "__main__":
    test_conditional_vasp_workflow_becomes_plan()
    test_sequential_regular_workflow_becomes_plan()
    test_single_vasp_submit_and_analyze_phrase_stays_single_intent()
    test_plan_formatter_mentions_no_auto_execution()
    test_confirm_step_resolves_to_saved_route_text()
    test_confirm_second_step_keeps_vasp_context()
    test_execute_all_selection_is_supported_for_safe_plan()
    test_execute_all_rejects_confirm_required_plan()
    print("All route planner checks passed.")
