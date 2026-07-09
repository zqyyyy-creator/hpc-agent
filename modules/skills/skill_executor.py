from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from modules.skills.skill_registry import SkillDefinition
from modules.routing.tool_dispatcher import dispatch_tool_request


@dataclass
class SkillExecutionContext:
    question: str
    intent: str = ""
    state: Any = None
    diagnoser: Any = None
    documents: list[str] | None = None
    sources: list[str] | None = None
    current_job_id: str | None = None


@dataclass
class SkillExecutionResult:
    answer: str
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)


def _import_dotted_path(dotted_path: str):
    if "." not in dotted_path:
        raise ValueError(f"Runtime handler is not a dotted path: {dotted_path}")

    module_name, attr_name = dotted_path.rsplit(".", 1)
    if not module_name or not attr_name:
        raise ValueError(f"Runtime handler is not a valid dotted path: {dotted_path}")

    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _runtime_handler(skill: SkillDefinition):
    return _import_dotted_path(skill.runtime.get("handler") or skill.handler)


def _execute_question_to_text(skill: SkillDefinition, context: SkillExecutionContext) -> SkillExecutionResult:
    handler = _runtime_handler(skill)
    answer = handler(context.question)
    return SkillExecutionResult(
        answer=str(answer),
        data={
            "runtime": {
                "adapter": "question_to_text",
                "handler": skill.runtime.get("handler") or skill.handler,
            },
        },
    )


def _execute_injected_diagnoser(skill: SkillDefinition, context: SkillExecutionContext) -> SkillExecutionResult:
    diagnoser = context.diagnoser
    if diagnoser is None:
        diagnoser_class = _runtime_handler(skill)
        diagnoser = diagnoser_class()

    answer = diagnoser.format_results(diagnoser.diagnose(context.question))
    return SkillExecutionResult(
        answer=str(answer),
        data={
            "runtime": {
                "adapter": "injected_diagnoser",
                "handler": skill.runtime.get("handler") or skill.handler,
            },
        },
    )


def _execute_tool_dispatch(skill: SkillDefinition, context: SkillExecutionContext) -> SkillExecutionResult:
    dispatch_result = dispatch_tool_request(
        context.question,
        context.intent,
        state=context.state,
    )
    data = dict(dispatch_result.data)
    if context.intent in {"job_output", "job_error"}:
        data["live_log"] = dispatch_result.message[-3000:]

    return SkillExecutionResult(
        answer=dispatch_result.message,
        success=dispatch_result.success,
        data={
            **data,
            "runtime": {
                "adapter": "tool_dispatch",
                "handler": skill.runtime.get("handler") or skill.handler,
            },
        },
    )


def _build_generate_vasp_inputs_pending_action(
    result: dict[str, Any],
    context: SkillExecutionContext,
) -> dict[str, Any] | None:
    if result.get("success") or not result.get("existing_files"):
        return None

    return {
        "kind": "generate_vasp_inputs_overwrite",
        "payload": {
            "job_dir": result.get("job_dir"),
            "user_request": context.question,
        },
        "description": "VASP 输入文件覆盖确认，回复“确认覆盖”或“覆盖已有配置文件”后执行；回复“取消覆盖”取消。",
    }


def _execute_structured_result(skill: SkillDefinition, context: SkillExecutionContext) -> SkillExecutionResult:
    handler = _runtime_handler(skill)
    raw_result = handler(context.question)
    if not isinstance(raw_result, dict):
        raise ValueError(f"Structured result skill {skill.name} returned {type(raw_result).__name__}, expected dict")

    result = dict(raw_result)
    message_field = skill.runtime.get("message_field", "message")
    success_field = skill.runtime.get("success_field", "success")
    answer = str(result.get(message_field, ""))
    success = bool(result.get(success_field, True))

    pending_action = None
    if skill.runtime.get("pending_action") == "generate_vasp_inputs_overwrite":
        pending_action = _build_generate_vasp_inputs_pending_action(result, context)

    if pending_action is not None:
        result["pending_action"] = pending_action
        result[message_field] = (
            answer
            + "\n\n如要覆盖并重新生成，请回复：“确认覆盖” 或 “覆盖已有配置文件”。"
            + "\n如果不想覆盖，请回复：“取消覆盖”。"
        )
        answer = result[message_field]

    result["runtime"] = {
        "adapter": "structured_result",
        "handler": skill.runtime.get("handler") or skill.handler,
        "message_field": message_field,
        "success_field": success_field,
    }
    return SkillExecutionResult(answer=answer, success=success, data=result)


def execute_skill(skill: SkillDefinition, context: SkillExecutionContext) -> SkillExecutionResult:
    adapter = skill.runtime.get("adapter", "")
    if adapter == "question_to_text":
        return _execute_question_to_text(skill, context)
    if adapter == "injected_diagnoser":
        return _execute_injected_diagnoser(skill, context)
    if adapter == "tool_dispatch":
        return _execute_tool_dispatch(skill, context)
    if adapter == "structured_result":
        return _execute_structured_result(skill, context)

    raise ValueError(f"Unsupported runtime adapter for skill {skill.name}: {adapter}")
