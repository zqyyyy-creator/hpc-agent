from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any

from modules.skills.skill_registry import SkillDefinition
from modules.routing.tool_dispatcher import dispatch_tool_request


DEFAULT_EXTERNAL_PYTHON_TIMEOUT_SECONDS = 10.0


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


def _load_external_python_handler_from_path(skill_name: str, skill_path: str, handler_decl: str):
    if not handler_decl.startswith("handler.") or handler_decl.count(".") != 1:
        raise ValueError(f"External skill {skill_name} handler must use format handler.function_name")

    _, function_name = handler_decl.split(".", 1)
    handler_path = os.path.join(os.path.dirname(skill_path), "handler.py")
    handler_path = os.path.abspath(handler_path)
    if not os.path.isfile(handler_path):
        raise ValueError(f"External skill {skill_name} handler.py does not exist: {handler_path}")

    module_name = f"hpc_agent_external_skill_{skill_name.replace('-', '_')}_{abs(hash(str(handler_path)))}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load external skill handler: {handler_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name, None)
    if not callable(handler):
        raise ValueError(f"External skill {skill_name} handler {function_name} is not callable.")
    return handler


def _load_external_python_handler(skill: SkillDefinition):
    if skill.source != "custom":
        raise ValueError(f"Skill {skill.name} is not an external custom skill.")
    if skill.runtime.get("adapter") != "external_python":
        raise ValueError(f"Skill {skill.name} is not an external_python skill.")
    return _load_external_python_handler_from_path(skill.name, str(skill.path), skill.handler)


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _assert_external_python_trusted(skill: SkillDefinition) -> None:
    if not _truthy(os.getenv("HPC_AGENT_TRUST_EXTERNAL_PYTHON", "")):
        raise ValueError("External Python skills are disabled. Set HPC_AGENT_TRUST_EXTERNAL_PYTHON=true to enable.")
    if str(skill.metadata.get("trusted", "")).strip().lower() != "true":
        raise ValueError(f"External Python skill {skill.name} is missing trusted: true.")


def _external_skill_context(skill: SkillDefinition, context: SkillExecutionContext) -> dict[str, Any]:
    env_names = [
        "HPC_HOST",
        "HPC_USERNAME",
        "HPC_REMOTE_WORKDIR",
        "HPC_LOCAL_WORKDIR",
        "HPC_DEFAULT_PARTITION",
        "HPC_VASP_PARTITION",
    ]
    return {
        "question": context.question,
        "intent": context.intent,
        "skill_name": skill.name,
        "skill_dir": str(skill.path.parent),
        "skill_path": str(skill.path),
        "description": skill.description,
        "triggers": list(skill.triggers),
        "metadata": dict(skill.metadata),
        "env": {name: os.getenv(name, "") for name in env_names},
        "current_job_id": context.current_job_id,
    }


def _external_python_timeout_seconds(skill: SkillDefinition) -> float:
    raw_value = (
        skill.runtime.get("timeout_seconds")
        or os.getenv("HPC_AGENT_EXTERNAL_PYTHON_TIMEOUT_SECONDS", "")
        or str(DEFAULT_EXTERNAL_PYTHON_TIMEOUT_SECONDS)
    )
    try:
        timeout = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid external_python timeout_seconds: {raw_value!r}")
    if timeout <= 0:
        raise ValueError("external_python timeout_seconds must be greater than 0")
    return min(timeout, 300.0)


def _run_external_python_handler_with_timeout(
    skill: SkillDefinition,
    context_payload: dict[str, Any],
    *,
    timeout_seconds: float,
) -> Any:
    payload = {
        "skill": {
                "name": skill.name,
                "path": str(skill.path),
                "handler": skill.handler,
        },
        "context": context_payload,
    }

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        payload_path = handle.name

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "modules.skills.external_python_runner",
                payload_path,
            ],
            cwd=os.getcwd(),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(
            f"External Python skill {skill.name} timed out after {timeout_seconds:g} seconds."
        ) from error
    finally:
        try:
            os.unlink(payload_path)
        except OSError:
            pass

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        raise RuntimeError(
            f"External Python skill {skill.name} runner exited with code {completed.returncode}: {stderr}"
        )

    try:
        result = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"External Python skill {skill.name} returned invalid runner JSON: {completed.stdout[-500:]}"
        ) from error

    if not result.get("ok"):
        raise RuntimeError(f"{result.get('error_type')}: {result.get('error')}")
    return result.get("raw_result")


def _normalize_external_python_result(skill: SkillDefinition, raw_result: Any) -> SkillExecutionResult:
    if isinstance(raw_result, str):
        return SkillExecutionResult(
            answer=raw_result,
            success=True,
            data={
                "runtime": {
                    "adapter": "external_python",
                    "handler": skill.handler,
                },
            },
        )
    if not isinstance(raw_result, dict):
        raise ValueError(
            f"External skill {skill.name} returned {type(raw_result).__name__}, expected str or dict"
        )

    result = dict(raw_result)
    answer = str(result.get("message") or result.get("answer") or "")
    if not answer:
        answer = f"外部 Skill `{skill.name}` 执行完成，但没有返回 message。"
    success = bool(result.get("success", True))
    data = dict(result.get("data") or {})
    data.update({
        "external_skill_result": result,
        "runtime": {
            "adapter": "external_python",
            "handler": skill.handler,
        },
    })
    return SkillExecutionResult(answer=answer, success=success, data=data)


def _execute_external_python(skill: SkillDefinition, context: SkillExecutionContext) -> SkillExecutionResult:
    if skill.risk != "read_only":
        raise ValueError(f"External Python skill {skill.name} must be read_only.")
    _assert_external_python_trusted(skill)

    timeout_seconds = _external_python_timeout_seconds(skill)
    raw_result = _run_external_python_handler_with_timeout(
        skill,
        _external_skill_context(skill, context),
        timeout_seconds=timeout_seconds,
    )
    result = _normalize_external_python_result(skill, raw_result)
    result.data.setdefault("runtime", {})
    result.data["runtime"]["timeout_seconds"] = timeout_seconds
    return result


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
    if adapter == "external_python":
        return _execute_external_python(skill, context)

    raise ValueError(f"Unsupported runtime adapter for skill {skill.name}: {adapter}")
