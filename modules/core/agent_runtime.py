from dataclasses import dataclass, field
import shlex
from typing import Any

from modules.knowledge.error_case_manager import build_error_case_draft
from modules.knowledge.knowledge_base import ask_llm, retrieve
from modules.core.environment_status import (
    check_hpc_environment,
    format_current_model_and_config,
    format_hpc_environment_check,
)
from modules.core.project_doctor import format_project_doctor, run_project_doctor
from modules.routing.router import expand_shortcut_command, get_clarification
from modules.slurm.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.routing.tool_dispatcher import dispatch_tool_request
from modules.skills.skill_executor import SkillExecutionContext, execute_skill
from modules.skills.skill_registry import SkillDefinition, load_skill_registry
from modules.vasp.vasp_assistant import generate_vasp_sbatch_script
from modules.slurm.job_query import (
    analyze_vasp_job,
    diagnose_job_request,
    extract_job_id,
    generate_vasp_report,
    query_remote_agent_jobs,
    query_remote_vasp_jobs,
)
from modules.slurm.job_lifecycle import (
    build_archive_job_records_preview,
    build_restore_job_records_preview,
    format_job_detail_for_request,
    format_job_record_archives,
    format_job_record_status,
    format_recent_jobs,
    format_vasp_jobs,
)


ANSWER_INTENTS = {
    "rag_qa",
    "clarify",
    "shortcut_help",
    "project_doctor",
    "generate_sbatch",
    "current_config",
    "check_hpc_config",
    "generate_vasp_job",
    "generate_vasp_inputs",
    "generate_vasp_report",
    "analyze_vasp_job",
    "list_remote_jobs",
    "list_remote_vasp_jobs",
    "suggest_params",
    "check_local_resources",
    "diagnose_error",
    "prepare_error_case",
    "diagnose_job",
    "troubleshoot_job",
    "register_vasp_job",
    "sync_vasp_output",
    "job_status",
    "job_output",
    "job_error",
    "recent_jobs",
    "job_record_status",
    "preview_archive_job_records",
    "list_job_record_archives",
    "preview_restore_job_records",
    "job_detail",
    "list_local_vasp_jobs",
}

CLEANUP_PREVIEW_INTENTS = {
    "cleanup_remote_job",
    "cleanup_all_remote_jobs",
    "cleanup_remote_vasp_job",
    "cleanup_all_remote_vasp_jobs",
}

CLEANUP_PENDING_KINDS = {
    "cleanup_remote_job": "job",
    "cleanup_all_remote_jobs": "all",
    "cleanup_remote_vasp_job": "vasp_job",
    "cleanup_all_remote_vasp_jobs": "vasp_all",
}

CLEANUP_PENDING_DESCRIPTIONS = {
    "cleanup_remote_job": "远端清理预览，回复“确认执行”或“确认清理”后执行。",
    "cleanup_all_remote_jobs": "远端全部清理预览，回复“确认执行”或“确认清理全部”后执行。",
    "cleanup_remote_vasp_job": "远端 VASP 清理预览，回复“确认执行”或“确认清理”后执行。",
    "cleanup_all_remote_vasp_jobs": "远端 VASP 全部清理预览，回复“确认执行”或“确认清理全部”后执行。",
}

SUBMIT_PREVIEW_INTENTS = {"submit_job", "submit_vasp_job", "test_hpc_submission"}
_SKILL_REGISTRY = None
_SKILL_REGISTRY_ERROR = ""

SYSTEM_CONTROL_SHORTCUT_PREFIXES = (
    "/help",
    "/doctor",
    "/config",
    "/model",
    "/resources",
    "/skill",
)

EXTERNAL_PYTHON_PROTECTED_INTENTS = {
    "shortcut_help",
    "project_doctor",
    "current_config",
    "prepare_error_case",
    "preview_archive_job_records",
    "preview_restore_job_records",
    "generate_vasp_inputs",
}


def can_preview_submit_intent(intent: str) -> bool:
    return intent in SUBMIT_PREVIEW_INTENTS


def _get_skill_registry():
    global _SKILL_REGISTRY, _SKILL_REGISTRY_ERROR
    if _SKILL_REGISTRY is None:
        try:
            _SKILL_REGISTRY = load_skill_registry()
            _SKILL_REGISTRY_ERROR = ""
        except Exception as error:
            _SKILL_REGISTRY = False
            _SKILL_REGISTRY_ERROR = f"{type(error).__name__}: {error}"
    return _SKILL_REGISTRY or None


def get_skill_registry_error() -> str:
    _get_skill_registry()
    return _SKILL_REGISTRY_ERROR


def _skill_info(skill: SkillDefinition) -> dict[str, Any]:
    return {
        "name": skill.name,
        "type": skill.type,
        "intents": list(skill.intents),
        "triggers": list(skill.triggers),
        "handler": skill.handler,
        "runtime": dict(skill.runtime),
        "path": str(skill.path),
        "description": skill.description,
        "source": skill.source,
        "risk": skill.risk,
    }


def get_skill_info_for_intent(intent: str) -> dict[str, Any] | None:
    registry = _get_skill_registry()
    if registry is None:
        return None

    skill = registry.get_by_intent(intent)
    if skill is None:
        return None
    return _skill_info(skill)


def _prompt_skills_for_question(question: str) -> list[SkillDefinition]:
    registry = _get_skill_registry()
    if registry is None:
        return []
    return registry.prompt_skills_for_question(question)


def _prompt_skill_context_for_question(question: str) -> tuple[list[SkillDefinition], list[dict[str, Any]]]:
    skills = _prompt_skills_for_question(question)
    return skills, [_skill_info(skill) for skill in skills]


def _external_python_skills_for_question(question: str) -> list[SkillDefinition]:
    if question.strip().lower().startswith("/skill test"):
        return []
    registry = _get_skill_registry()
    if registry is None:
        return []
    return registry.external_python_skills_for_question(question)


def _is_system_control_shortcut(question: str) -> bool:
    stripped = question.strip().lower()
    return any(
        stripped == prefix or stripped.startswith(f"{prefix} ")
        for prefix in SYSTEM_CONTROL_SHORTCUT_PREFIXES
    )


def should_consider_external_python_skill(question: str, intent: str) -> bool:
    """Fixed priority rule for external read_only Python skills.

    Priority:
    1. Slash system/control commands stay builtin.
    2. Confirm-required/destructive/overwrite-style builtin operations stay builtin.
    3. External read_only Python skills may preempt ordinary answer intents.
    4. Builtin read-only tools run when no external Python skill matches.
    5. Prompt-only skills are injected only into the final RAG answer path.
    """
    if _is_system_control_shortcut(question):
        return False
    if intent in EXTERNAL_PYTHON_PROTECTED_INTENTS:
        return False
    return can_answer_intent(intent)


@dataclass
class AgentRuntimeResult:
    handled: bool
    intent: str
    answer: str = ""
    success: bool = True
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.handled:
            return

        skill = get_skill_info_for_intent(self.intent)
        if skill is not None:
            self.data.setdefault("skill", skill)


def can_answer_intent(intent: str) -> bool:
    if intent in ANSWER_INTENTS:
        return True

    registry = _get_skill_registry()
    return bool(registry and registry.get_by_intent(intent))


def _execute_registered_skill(
    question: str,
    intent: str,
    *,
    documents,
    sources,
    diagnoser,
    state,
    current_job_id: str | None = None,
) -> AgentRuntimeResult | None:
    registry = _get_skill_registry()
    if registry is None:
        return None

    skill = registry.get_by_intent(intent)
    if skill is None:
        return None

    if (
        skill.runtime.get("adapter") == "tool_dispatch"
        and current_job_id
        and intent in {"job_status", "job_output", "job_error"}
        and state is not None
        and not extract_job_id(question)
    ):
        state.record_job(current_job_id, metadata={"source": "ui_context"})

    context = SkillExecutionContext(
        question=question,
        intent=intent,
        state=state,
        diagnoser=diagnoser,
        documents=documents,
        sources=sources,
        current_job_id=current_job_id,
    )
    try:
        result = execute_skill(skill, context)
    except Exception as error:
        return _fallback_after_skill_failure(
            question,
            intent,
            skill,
            error,
            documents=documents,
            sources=sources,
            state=state,
        )
    else:
        return AgentRuntimeResult(
            True,
            intent,
            result.answer,
            success=result.success,
            data=result.data,
        )


def _execute_external_python_skill(
    question: str,
    intent: str,
    *,
    documents,
    sources,
    diagnoser,
    state,
    current_job_id: str | None = None,
    control_question: str | None = None,
) -> AgentRuntimeResult | None:
    if not should_consider_external_python_skill(control_question or question, intent):
        return None

    skills = _external_python_skills_for_question(question)
    if not skills:
        return None

    skill = skills[0]
    skill_info = _skill_info(skill)
    pending_action = {
        "kind": "external_python_skill",
        "payload": {
            "skill_name": skill.name,
            "skill_path": str(skill.path),
            "question": question,
            "current_job_id": current_job_id,
        },
        "description": f"外部 Python Skill `{skill.name}` 执行确认。",
    }

    return AgentRuntimeResult(
        True,
        intent,
        "\n".join([
            f"检测到外部 Python Skill：{skill.name}",
            f"说明：{skill.description}",
            f"来源：{skill.path.parent}",
            f"风险等级：{skill.risk or 'unknown'}",
            "",
            "该 Skill 将在确认后执行本地 handler.py。",
            "如要执行，请回复“确认执行”或“确认”。",
            "如不执行，请回复“取消”。",
        ]),
        success=True,
        data={
            "skill": skill_info,
            "external_skills": [skill_info],
            "pending_action": pending_action,
        },
    )


def _run_external_python_skill_now(
    question: str,
    intent: str,
    skill: SkillDefinition,
    *,
    documents,
    sources,
    diagnoser,
    state,
    current_job_id: str | None = None,
) -> AgentRuntimeResult:
    context = SkillExecutionContext(
        question=question,
        intent=intent,
        state=state,
        diagnoser=diagnoser,
        documents=documents,
        sources=sources,
        current_job_id=current_job_id,
    )

    try:
        result = execute_skill(skill, context)
    except Exception as error:
        return AgentRuntimeResult(
            True,
            intent,
            "\n".join([
                f"外部 Skill `{skill.name}` 执行失败，未执行其它外部代码。",
                "",
                f"错误: {type(error).__name__}: {error}",
            ]),
            success=False,
            data={
                "skill": _skill_info(skill),
                "external_skills": [_skill_info(skill)],
                "error": f"{type(error).__name__}: {error}",
            },
        )

    data = dict(result.data)
    data.setdefault("skill", _skill_info(skill))
    data.setdefault("external_skills", [_skill_info(skill)])
    return AgentRuntimeResult(
        True,
        intent,
        result.answer,
        success=result.success,
        data=data,
    )


def _fallback_after_skill_failure(
    question: str,
    intent: str,
    skill: SkillDefinition,
    error: Exception,
    *,
    documents,
    sources,
    state,
) -> AgentRuntimeResult:
    error_summary = f"{type(error).__name__}: {error}"
    data = {
        "skill_fallback": True,
        "failed_skill": _skill_info(skill),
        "error": error_summary,
    }

    try:
        docs = retrieve(question, documents, sources)
    except Exception as retrieve_error:
        data["fallback_error"] = f"{type(retrieve_error).__name__}: {retrieve_error}"
        return AgentRuntimeResult(
            True,
            intent,
            "\n".join([
                f"Skill `{skill.name}` 执行失败，尝试切换到知识库回答时也失败了。",
                "",
                f"Skill 错误: {error_summary}",
                f"RAG 错误: {data['fallback_error']}",
            ]),
            success=False,
            data=data,
        )

    if docs:
        try:
            prompt_skills, prompt_skill_info = _prompt_skill_context_for_question(question)
            if prompt_skill_info:
                data["prompt_skills"] = prompt_skill_info
            fallback_answer = ask_llm(
                question,
                docs,
                conversation_state=state,
                prompt_skills=prompt_skills,
            )
        except Exception as llm_error:
            data["fallback_error"] = f"{type(llm_error).__name__}: {llm_error}"
            return AgentRuntimeResult(
                True,
                intent,
                "\n".join([
                    f"Skill `{skill.name}` 执行失败，已检索到知识库内容，但生成回答失败。",
                    "",
                    f"Skill 错误: {error_summary}",
                    f"回答生成错误: {data['fallback_error']}",
                ]),
                success=False,
                data=data,
            )

        data["fallback_retrieval"] = [
            {"source": item.get("source"), "score": item.get("score")}
            for item in docs
        ]
        return AgentRuntimeResult(
            True,
            intent,
            "\n".join([
                f"Skill `{skill.name}` 执行失败，已切换到知识库回答。",
                "",
                fallback_answer,
            ]),
            success=True,
            data=data,
        )

    return AgentRuntimeResult(
        True,
        intent,
        "\n".join([
            f"Skill `{skill.name}` 执行失败，当前没有检索到可用知识库内容，未执行原操作。",
            "",
            f"错误: {error_summary}",
        ]),
        success=False,
        data=data,
    )


def can_preview_cleanup_intent(intent: str) -> bool:
    return intent in CLEANUP_PREVIEW_INTENTS


def _skill_trigger_matches(skill: SkillDefinition, question: str) -> bool:
    question_norm = "".join(str(question).lower().split())
    candidates = list(skill.triggers)
    candidates.append(skill.name)
    for candidate in candidates:
        candidate_norm = "".join(str(candidate).lower().split())
        if len(candidate_norm) >= 2 and candidate_norm in question_norm:
            return True
    return False


def _parse_skill_test_command(question: str) -> tuple[str, str] | None:
    stripped = question.strip()
    if not stripped.lower().startswith("/skill test"):
        return None
    tail = stripped[len("/skill test"):].strip()
    if not tail:
        return None
    try:
        parts = shlex.split(tail)
    except ValueError:
        parts = tail.split(maxsplit=1)
    if not parts:
        return None
    skill_name = parts[0]
    test_question = " ".join(parts[1:]).strip()
    return skill_name, test_question


def _format_skill_test_loaded_line(skill: SkillDefinition, test_question: str = "") -> str:
    adapter = skill.runtime.get("adapter", "prompt-only" if skill.type == "prompt" and not skill.handler else "-")
    trigger_text = ", ".join(skill.triggers) or "-"
    trigger_match = "-"
    if test_question:
        trigger_match = "YES" if _skill_trigger_matches(skill, test_question) else "NO"

    parts = [
        f"- {skill.name}",
        f"状态=LOADED",
        f"type={skill.type}",
        f"source={skill.source}",
        f"adapter={adapter}",
        f"triggers={trigger_text}",
        f"trigger命中={trigger_match}",
    ]

    if adapter == "external_python":
        handler_path = skill.path.parent / "handler.py"
        parts.extend([
            f"handler={skill.handler}",
            f"handler.py={'YES' if handler_path.is_file() else 'NO'}",
            f"trusted={skill.metadata.get('trusted', 'false')}",
            f"timeout={skill.runtime.get('timeout_seconds') or 'env/default'}",
        ])
    return " | ".join(parts)


def _format_skill_test_all(registry, test_question: str = "") -> str:
    loaded = sorted(registry.all(), key=lambda item: (item.source, item.name))
    skipped = sorted(registry.skipped(), key=lambda item: item.name or item.path.name)
    external_python_count = sum(1 for skill in loaded if skill.runtime.get("adapter") == "external_python")
    prompt_only_count = sum(1 for skill in loaded if skill.source == "custom" and skill.type == "prompt" and not skill.handler)

    lines = [
        "Skill dry-run 总览",
        "",
        f"已加载: {len(loaded)}",
        f"外部 prompt-only: {prompt_only_count}",
        f"外部 external_python: {external_python_count}",
        f"已跳过: {len(skipped)}",
        f"测试问题: {test_question or '-'}",
        "",
        "说明: 这是 dry-run，只检查加载状态、trigger 和 handler 配置，不执行 handler.py。",
        "",
        "已加载 Skills:",
    ]
    if loaded:
        lines.extend(_format_skill_test_loaded_line(skill, test_question) for skill in loaded)
    else:
        lines.append("- 无")

    lines.append("")
    lines.append("已跳过 Skills:")
    if skipped:
        for item in skipped:
            lines.append(f"- {item.name or item.path.parent.name}: {item.reason} ({item.path})")
    else:
        lines.append("- 无")

    return "\n".join(lines)


def _format_skill_test(question: str) -> str:
    parsed = _parse_skill_test_command(question)
    if parsed is None:
        return "用法: /skill test <skill-name> \"测试问题\" 或 /skill test all"

    skill_name, test_question = parsed
    registry = _get_skill_registry()
    lines = [
        "Skill dry-run 测试",
        "",
        f"Skill: {skill_name}",
        f"测试问题: {test_question or '-'}",
        "",
    ]
    if registry is None:
        lines.append("SkillRegistry 加载失败，无法测试。")
        error = get_skill_registry_error()
        if error:
            lines.append(f"失败原因: {error}")
        return "\n".join(lines)

    if skill_name.lower() in {"all", "--all", "*"}:
        return _format_skill_test_all(registry, test_question)

    skipped = next((item for item in registry.skipped() if item.name == skill_name or item.path.parent.name == skill_name), None)
    skill = registry.get(skill_name)

    if skipped is not None:
        lines.extend([
            "状态: SKIPPED",
            f"路径: {skipped.path}",
            f"跳过原因: {skipped.reason}",
        ])
        return "\n".join(lines)

    if skill is None:
        lines.append("状态: NOT FOUND")
        lines.append("提示: 运行 /skill list 查看已加载和已跳过的外部 Skills。")
        return "\n".join(lines)

    trigger_match = _skill_trigger_matches(skill, test_question) if test_question else False
    lines.extend([
        "状态: LOADED",
        f"类型: {skill.type}",
        f"来源: {skill.source}",
        f"路径: {skill.path}",
        f"风险等级: {skill.risk or '-'}",
        f"triggers: {', '.join(skill.triggers) or '-'}",
        f"trigger 命中: {'YES' if trigger_match else 'NO'}",
    ])

    if skill.runtime.get("adapter") == "external_python":
        handler_path = skill.path.parent / "handler.py"
        lines.extend([
            "adapter: external_python",
            f"handler: {skill.handler}",
            f"handler.py 存在: {'YES' if handler_path.is_file() else 'NO'}",
            f"trusted: {skill.metadata.get('trusted', 'false')}",
            f"timeout_seconds: {skill.runtime.get('timeout_seconds') or 'env/default'}",
            "",
            "dry-run 结果: 仅检查配置和 trigger，不执行 handler.py。",
        ])
    elif skill.source == "custom" and skill.type == "prompt" and not skill.handler:
        body_preview = skill.body[:160].replace("\n", " ")
        lines.extend([
            "adapter: prompt-only",
            f"正文预览: {body_preview}",
        ])
    else:
        lines.extend([
            f"intents: {', '.join(skill.intents) or '-'}",
            f"runtime.adapter: {skill.runtime.get('adapter', '-')}",
        ])

    return "\n".join(lines)


def format_shortcut_help(question: str = "") -> str:
    normalized = question.strip().lower().replace(" ", "")
    if question.strip().lower().startswith("/skill test"):
        return _format_skill_test(question)

    if normalized == "/helpjob":
        return "\n".join([
            "Job 快捷命令",
            "",
            "/job recent                 查看最近作业",
            "/job status <job_id>        查看作业状态",
            "/job out <job_id>           读取标准输出",
            "/job err <job_id>           读取错误日志",
            "/job detail <job_id>        查看作业详情",
            "/job diagnose <job_id>      诊断作业",
            "/job monitor <job_id>       开始在 TUI 右侧监控 Job",
            "/job stop-monitor <job_id>  取消 TUI 右侧监控",
            "/job records                查看本地作业记录状态",
            "/job archive --keep 100     预览归档本地作业记录",
            "/job archives               查看归档记录",
            "/job restore                预览恢复最近一次归档",
            "",
            "说明: 这些是推荐快捷写法；当前也可以继续用自然语言表达同样操作。",
        ])

    if normalized == "/helpvasp":
        return "\n".join([
            "VASP 快捷命令",
            "",
            "/vasp list                  列出本地记录的 VASP 作业",
            "/vasp jobs                  列出本地记录的 VASP 作业",
            "/vasp gen <name>            根据已有 POTCAR 生成 INCAR/KPOINTS/POSCAR",
            "/vasp inputs <name>         根据已有 POTCAR 生成 INCAR/KPOINTS/POSCAR",
            "/vasp gen <name> --encut 400 --kpoints 2x2x2 --type static",
            "/vasp submit <name>         提交 VASP 作业",
            "/vasp sync <job_id>         同步 VASP 输出到本地",
            "/vasp analyze <job_id>      同步并分析 VASP 作业",
            "/vasp report <job_id|name>  生成 VASP 报告",
            "/vasp remote                查看远端 VASP input/output 目录",
            "/vasp clean <job_id|name>   预览清理远端 VASP 作业",
            "",
            "说明: POTCAR 仍需要来自你有权限使用的赝势库；快捷命令不会绕过提交或清理确认。",
        ])

    if normalized == "/helpcleanup":
        return "\n".join([
            "清理快捷命令",
            "",
            "/clean job <job_id>         预览清理远端普通作业文件",
            "/clean jobs                 预览清理远端普通作业根目录",
            "/clean vasp <job_id|name>   预览清理远端 VASP 作业",
            "/clean vasp-all             预览清理全部远端 VASP 作业",
            "",
            "说明: 清理类命令只会先生成预览，仍需要确认后才会执行。",
        ])

    if normalized == "/helpconfig":
        return "\n".join([
            "配置快捷命令",
            "",
            "/config                     查看当前模型和主要目录配置",
            "/config check               检查超算配置",
            "/model                      查看当前模型",
            "",
            "说明: 配置输出会隐藏 API Key 明文。",
        ])

    if normalized == "/helpskill" or normalized == "/skilllist":
        registry = _get_skill_registry()
        lines = [
            "Skill 快捷命令",
            "",
            "/skill list                 查看已注册 Skill",
            "/skill route <question>     查看一句话会被路由到哪个 Skill",
            "/skill test <name> \"问题\"   dry-run 检查外部 Skill 是否加载、trigger 是否命中",
            "/skill test all             dry-run 检查所有 Skill",
            "",
        ]
        if registry is None:
            error = get_skill_registry_error()
            lines.append("当前 SkillRegistry 加载失败，请运行：.venv/bin/python tools/skill_debug.py --validate")
            if error:
                lines.append(f"失败原因: {error}")
            return "\n".join(lines)

        lines.append("当前已注册 Skill:")
        for skill in sorted(registry.all(), key=lambda item: item.name):
            if skill.source == "custom" and skill.runtime.get("adapter") == "external_python":
                detail = f"external_python triggers={', '.join(skill.triggers)}"
            elif skill.source == "custom" and skill.type == "prompt" and not skill.handler:
                detail = f"prompt triggers={', '.join(skill.triggers)}"
            else:
                detail = ", ".join(skill.intents)
            lines.append(f"- {skill.name}: {detail}")
        skipped_skills = registry.skipped()
        if skipped_skills:
            lines.extend(["", "已跳过的外部 Skills:"])
            for item in skipped_skills:
                lines.append(f"- {item.name or item.path.name}: {item.reason} ({item.path})")
        lines.extend([
            "",
            "完整校验命令: .venv/bin/python tools/skill_debug.py --validate",
        ])
        return "\n".join(lines)

    if normalized.startswith("/skillroute"):
        route_text = question.strip()[len("/skill route"):].strip()
        if route_text:
            return "\n".join([
                "Skill 路由调试",
                "",
                f"待检查问题: {route_text}",
                "",
                "在终端运行:",
                f'.venv/bin/python tools/skill_debug.py --route "{route_text}" --validate',
            ])
        return "用法: /skill route <question>"

    return "\n".join([
        "常用快捷命令",
        "",
        "/job recent                 查看最近作业",
        "/job detail <job_id>        查看作业详情",
        "/job diagnose <job_id>      诊断作业",
        "/job monitor <job_id>       开始监控 Job",
        "",
        "/vasp gen <name>            根据已有 POTCAR 生成 VASP 输入文件",
        "/vasp inputs <name>         根据已有 POTCAR 生成 VASP 输入文件",
        "/vasp submit <name>         提交 VASP 作业",
        "/vasp analyze <job_id>      同步并分析 VASP 作业",
        "",
        "/resources                  检查本机 CPU、内存、磁盘和 GPU",
        "/doctor                     运行项目总体体检",
        "/skill list                 查看已注册 Skill",
        "/skill test <name> \"问题\"   dry-run 检查外部 Skill",
        "/skill test all             dry-run 检查所有 Skill",
        "",
        "/config check               检查超算配置",
        "/model                      查看当前模型",
        "",
        "输入 /help job、/help vasp 或 /help skill 查看更多。",
    ])


def _cleanup_pending_payload(intent: str, dispatch_data: dict[str, Any]) -> dict[str, Any]:
    job_id = dispatch_data.get("job_id")

    if intent == "cleanup_remote_vasp_job":
        job_id = dispatch_data.get("selector")

    if intent in {"cleanup_all_remote_jobs", "cleanup_all_remote_vasp_jobs"}:
        job_id = None

    return {
        "kind": CLEANUP_PENDING_KINDS[intent],
        "targets": dispatch_data.get("targets", []),
        "job_id": job_id,
    }


def execute_cleanup_preview(question: str, intent: str, *, state) -> AgentRuntimeResult:
    if not can_preview_cleanup_intent(intent):
        return AgentRuntimeResult(handled=False, intent=intent, success=False)

    dispatch_result = dispatch_tool_request(question, intent, state=state)
    data = dict(dispatch_result.data)
    pending_cleanup = (
        _cleanup_pending_payload(intent, data)
        if data.get("ready")
        else None
    )

    data["pending_cleanup"] = pending_cleanup
    data["pending_action_description"] = CLEANUP_PENDING_DESCRIPTIONS[intent]
    data["requires_confirmation"] = bool(pending_cleanup)

    return AgentRuntimeResult(
        True,
        intent,
        dispatch_result.message,
        success=dispatch_result.success,
        data=data,
    )


def _format_file_list(uploaded_files: list[dict[str, Any]], prefix: str) -> str:
    if not uploaded_files:
        return ""

    return prefix + "\n".join(
        f"- {item['name']} ({len(item['content'])} bytes)"
        for item in uploaded_files
    )


def execute_submit_preview(
    question: str,
    intent: str,
    *,
    state,
    uploaded_files: list[dict[str, Any]] | None = None,
    source_text: str | None = None,
    inferred_command: str | None = None,
    recommendation_details: list[str] | None = None,
    auto_analyze: bool = False,
    pending_kind: str | None = None,
    confirmation_text: str = "\n\n回复“确认提交”后，我会连接超算执行 sbatch。\n回复“取消提交”可以放弃本次提交。",
    uploaded_note_prefix: str = "\n\n将上传附件:\n",
) -> AgentRuntimeResult:
    question = expand_shortcut_command(question)

    if not can_preview_submit_intent(intent):
        return AgentRuntimeResult(handled=False, intent=intent, success=False)

    uploaded_files = list(uploaded_files or [])
    dispatch_intent = "submit_job" if intent == "test_hpc_submission" else intent
    dispatch_question = question

    dispatch_result = dispatch_tool_request(
        dispatch_question,
        dispatch_intent,
        state=state,
        uploaded_files=uploaded_files,
        source_text=source_text or dispatch_question,
    )
    prepared = dispatch_result.data["prepared"]
    data = dict(dispatch_result.data)

    if not prepared.get("ready"):
        data["pending_submission"] = None
        data["requires_confirmation"] = False
        return AgentRuntimeResult(
            True,
            intent,
            prepared.get("message", ""),
            success=False,
            data=data,
        )

    if intent == "submit_vasp_job":
        pending_submission = {
            "kind": pending_kind or "vasp",
            "script": data["script"],
            "source_text": data["source_text"],
            "uploaded_files": data["uploaded_files"],
            "auto_analyze": auto_analyze,
        }
        workflow_note = ""
        if auto_analyze:
            workflow_note = (
                "\n\n检测到“运行并分析”请求。确认提交后将自动进入长流程："
                "\n监控 Slurm/VASP 输出 -> 作业结束后同步输出 -> 调用 Claude Code 生成报告。"
            )
        answer = f"{prepared['message']}{workflow_note}{confirmation_text}"
    else:
        pending_submission = {
            "kind": pending_kind or "slurm",
            "script": data["script"],
            "uploaded_files": data["uploaded_files"],
            "source_text": data["source_text"],
        }
        command_note = f"\n\n推断运行命令: {inferred_command}" if inferred_command else ""
        resource_note = ""
        if recommendation_details:
            resource_note = "\n\nAgent 推荐资源:\n" + "\n".join(
                f"- {item}" for item in recommendation_details
            )
        uploaded_note = _format_file_list(data["uploaded_files"], uploaded_note_prefix)
        intro = ""
        if intent == "test_hpc_submission":
            intro = (
                "我将用一个最小 hostname 作业测试普通 Slurm 提交流程。"
                "这只会提交一个短作业，用来验证 sbatch、远端目录和日志链路。\n\n"
            )
        answer = f"{intro}{prepared['message']}{command_note}{resource_note}{uploaded_note}{confirmation_text}"

    data["pending_submission"] = pending_submission
    data["requires_confirmation"] = True
    data["pending_action_description"] = "作业提交预览，回复“确认执行”或“确认提交”后执行。"

    return AgentRuntimeResult(
        True,
        intent,
        answer,
        success=True,
        data=data,
    )


def execute_answer_intent(
    question: str,
    intent: str,
    *,
    documents,
    sources,
    diagnoser,
    state,
    no_docs_message: str | None = None,
    current_job_id: str | None = None,
) -> AgentRuntimeResult:
    raw_question = question
    question = expand_shortcut_command(question)

    if question.strip().lower().startswith("/skill test"):
        return AgentRuntimeResult(True, "shortcut_help", format_shortcut_help(question))

    if not can_answer_intent(intent):
        return AgentRuntimeResult(handled=False, intent=intent, success=False)

    if intent == "clarify":
        return AgentRuntimeResult(True, intent, get_clarification(question), success=False)

    if intent == "shortcut_help":
        return AgentRuntimeResult(True, intent, format_shortcut_help(question))

    if intent == "project_doctor":
        result = run_project_doctor(documents=documents, sources=sources)
        return AgentRuntimeResult(
            True,
            intent,
            format_project_doctor(result),
            success=result["success"],
            data=result,
        )

    external_skill_result = _execute_external_python_skill(
        question,
        intent,
        documents=documents,
        sources=sources,
        diagnoser=diagnoser,
        state=state,
        current_job_id=current_job_id,
        control_question=raw_question,
    )
    if external_skill_result is not None:
        return external_skill_result

    skill_result = _execute_registered_skill(
        question,
        intent,
        documents=documents,
        sources=sources,
        diagnoser=diagnoser,
        state=state,
        current_job_id=current_job_id,
    )
    if skill_result is not None:
        return skill_result

    if intent == "generate_sbatch":
        return AgentRuntimeResult(True, intent, generate_sbatch_script(question))

    if intent == "current_config":
        return AgentRuntimeResult(True, intent, format_current_model_and_config())

    if intent == "check_hpc_config":
        result = check_hpc_environment()
        return AgentRuntimeResult(
            True,
            intent,
            format_hpc_environment_check(result),
            success=result["success"],
            data=result,
        )

    if intent == "generate_vasp_job":
        return AgentRuntimeResult(True, intent, generate_vasp_sbatch_script(question))

    if intent == "generate_vasp_report":
        return AgentRuntimeResult(True, intent, generate_vasp_report(question))

    if intent == "analyze_vasp_job":
        return AgentRuntimeResult(True, intent, analyze_vasp_job(question))

    if intent == "list_remote_jobs":
        return AgentRuntimeResult(True, intent, query_remote_agent_jobs())

    if intent == "list_remote_vasp_jobs":
        return AgentRuntimeResult(True, intent, query_remote_vasp_jobs())

    if intent == "recent_jobs":
        return AgentRuntimeResult(True, intent, format_recent_jobs())

    if intent == "job_record_status":
        return AgentRuntimeResult(True, intent, format_job_record_status())

    if intent == "preview_archive_job_records":
        preview = build_archive_job_records_preview(question)
        data = dict(preview)
        pending_action = None
        if preview.get("requires_confirmation"):
            pending_action = {
                "kind": "archive_job_records",
                "payload": {
                    "keep_count": preview.get("keep_count"),
                    "keep_job_ids": preview.get("keep_job_ids") or [],
                    "archive_job_ids": preview.get("archive_job_ids") or [],
                },
                "description": "本地作业记录归档预览，回复“确认归档本地作业记录”后执行。",
            }
        data["pending_action"] = pending_action
        return AgentRuntimeResult(
            True,
            intent,
            preview["message"],
            success=preview.get("success", True),
            data=data,
        )

    if intent == "list_job_record_archives":
        return AgentRuntimeResult(True, intent, format_job_record_archives())

    if intent == "preview_restore_job_records":
        preview = build_restore_job_records_preview(question)
        data = dict(preview)
        pending_action = None
        if preview.get("requires_confirmation"):
            pending_action = {
                "kind": "restore_job_records",
                "payload": {
                    "archive_path": preview.get("archive_path"),
                    "restore_job_ids": preview.get("restore_job_ids") or [],
                },
                "description": "本地作业记录恢复预览，回复“确认恢复本地作业记录归档”后执行。",
            }
        data["pending_action"] = pending_action
        return AgentRuntimeResult(
            True,
            intent,
            preview["message"],
            success=preview.get("success", True),
            data=data,
        )

    if intent == "job_detail":
        return AgentRuntimeResult(True, intent, format_job_detail_for_request(question, state=state))

    if intent == "list_local_vasp_jobs":
        return AgentRuntimeResult(True, intent, format_vasp_jobs())

    if intent == "suggest_params":
        return AgentRuntimeResult(True, intent, suggest_slurm_parameters(question))

    if intent == "diagnose_error":
        return AgentRuntimeResult(
            True,
            intent,
            diagnoser.format_results(diagnoser.diagnose(question)),
        )

    if intent == "prepare_error_case":
        result = build_error_case_draft(question, state=state, diagnoser=diagnoser)
        return AgentRuntimeResult(
            True,
            intent,
            result["message"],
            success=result["success"],
            data=result,
        )

    if intent == "diagnose_job":
        return AgentRuntimeResult(True, intent, diagnose_job_request(question, state=state))

    if intent in {"register_vasp_job", "sync_vasp_output", "job_status", "job_output", "job_error"}:
        if current_job_id and intent in {"job_status", "job_output", "job_error"} and not extract_job_id(question):
            state.record_job(current_job_id, metadata={"source": "ui_context"})

        dispatch_result = dispatch_tool_request(question, intent, state=state)
        data = dict(dispatch_result.data)

        if intent in {"job_output", "job_error"}:
            data["live_log"] = dispatch_result.message[-3000:]

        return AgentRuntimeResult(
            True,
            intent,
            dispatch_result.message,
            success=dispatch_result.success,
            data=data,
        )

    docs = retrieve(question, documents, sources)
    if not docs and no_docs_message is not None:
        return AgentRuntimeResult(True, intent, no_docs_message, success=False)

    prompt_skills, prompt_skill_info = _prompt_skill_context_for_question(question)
    return AgentRuntimeResult(
        True,
        intent,
        ask_llm(question, docs, conversation_state=state, prompt_skills=prompt_skills),
        data={"prompt_skills": prompt_skill_info} if prompt_skill_info else {},
    )
