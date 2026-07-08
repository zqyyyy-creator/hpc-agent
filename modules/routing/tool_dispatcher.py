from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE, ConversationState
from modules.slurm.hpc_test_files import handle_hpc_test_request
from modules.slurm.job_query import (
    execute_cleanup_prepare_tool_call,
    execute_job_query_tool_call,
    execute_vasp_postprocess_tool_call,
    handle_cleanup_prepare_request,
    handle_job_query_request,
    handle_vasp_postprocess_request,
    validate_job_query_tool_call,
    validate_vasp_postprocess_tool_call,
)
from modules.slurm.job_submitter import prepare_submit_script, prepare_vasp_submit_script
from modules.routing.router import detect_intent
from modules.core.tool_calling import ToolCall, ToolResult


TOOL_DISPATCH_INTENTS = {
    "submit_job",
    "submit_vasp_job",
    "generate_test_file",
    "job_status",
    "job_output",
    "job_error",
    "cleanup_remote_job",
    "cleanup_all_remote_jobs",
    "cleanup_remote_vasp_job",
    "cleanup_all_remote_vasp_jobs",
    "register_vasp_job",
    "sync_vasp_output",
}


@dataclass
class DispatchResult:
    handled: bool
    intent: str
    message: str = ""
    success: bool = False
    data: dict[str, Any] = field(default_factory=dict)
    tool_result: ToolResult | None = None


DispatcherHandlers = dict[str, Callable[..., Any]]


def can_dispatch_intent(intent: str) -> bool:
    return intent in TOOL_DISPATCH_INTENTS


def dispatch_tool_request(
    user_request: str,
    intent: str | None = None,
    *,
    state: ConversationState | None = None,
    handlers: DispatcherHandlers | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    source_text: str | None = None,
) -> DispatchResult:
    resolved_intent = intent or detect_intent(user_request)

    if not can_dispatch_intent(resolved_intent):
        return DispatchResult(handled=False, intent=resolved_intent)

    active_state = state or GLOBAL_CONVERSATION_STATE
    active_handlers = handlers or {}

    if resolved_intent == "submit_job":
        handler = active_handlers.get("submit_job", prepare_submit_script)
        prepared = handler(user_request)
        ready = bool(prepared.get("ready"))
        data = {
            "ready": ready,
            "prepared": prepared,
            "script": prepared.get("script"),
            "submission_kind": "slurm",
            "uploaded_files": list(uploaded_files or []),
            "source_text": source_text or user_request,
        }
        return DispatchResult(
            handled=True,
            intent=resolved_intent,
            success=ready,
            message=prepared.get("message", ""),
            data=data,
        )

    if resolved_intent == "submit_vasp_job":
        handler = active_handlers.get("submit_vasp_job", prepare_vasp_submit_script)
        prepared = handler(user_request)
        ready = bool(prepared.get("ready"))
        data = {
            "ready": ready,
            "prepared": prepared,
            "script": prepared.get("script"),
            "submission_kind": "vasp",
            "uploaded_files": [],
            "source_text": source_text or user_request,
            "local_jobs_dir": prepared.get("local_jobs_dir"),
            "remote_input_dir": prepared.get("remote_input_dir"),
            "remote_output_dir": prepared.get("remote_output_dir"),
        }
        return DispatchResult(
            handled=True,
            intent=resolved_intent,
            success=ready,
            message=prepared.get("message", ""),
            data=data,
        )

    if resolved_intent == "generate_test_file":
        handler = active_handlers.get("generate_test_file", handle_hpc_test_request)
        message = handler(user_request)
        return DispatchResult(
            handled=True,
            intent=resolved_intent,
            success=True,
            message=message,
        )

    if resolved_intent in {"job_status", "job_output", "job_error"}:
        handler = active_handlers.get("job_query", handle_job_query_request)
        result = handler(user_request, resolved_intent, state=active_state)
        return DispatchResult(
            handled=True,
            intent=resolved_intent,
            success=result.success,
            message=result.message,
            data=dict(result.data),
            tool_result=result,
        )

    if resolved_intent in {
        "cleanup_remote_job",
        "cleanup_all_remote_jobs",
        "cleanup_remote_vasp_job",
        "cleanup_all_remote_vasp_jobs",
    }:
        handler = active_handlers.get("cleanup", handle_cleanup_prepare_request)
        result = handler(user_request, resolved_intent)
        return DispatchResult(
            handled=True,
            intent=resolved_intent,
            success=result.success,
            message=result.message,
            data=dict(result.data),
            tool_result=result,
        )

    if resolved_intent in {"register_vasp_job", "sync_vasp_output"}:
        handler = active_handlers.get("vasp_postprocess", handle_vasp_postprocess_request)
        result = handler(user_request, resolved_intent, state=active_state)
        return DispatchResult(
            handled=True,
            intent=resolved_intent,
            success=result.success,
            message=result.message,
            data=dict(result.data),
            tool_result=result,
        )

    return DispatchResult(handled=False, intent=resolved_intent)


# ---------------------------------------------------------------------------
# LLM-classified intent dispatch — bypass the rule-based make_* stage
# and feed the LLM-produced ToolCall straight into validate → execute.
# ---------------------------------------------------------------------------

# Intent → (validate_func, execute_func)
# validate/execute take (tool_call, state=...) where state is a keyword.
_LLM_DISPATCH_TABLE: dict[str, tuple[Callable[..., Any], Callable[..., Any]]] = {
    "job_status": (validate_job_query_tool_call, execute_job_query_tool_call),
    "job_output": (validate_job_query_tool_call, execute_job_query_tool_call),
    "job_error": (validate_job_query_tool_call, execute_job_query_tool_call),
    "register_vasp_job": (validate_vasp_postprocess_tool_call, execute_vasp_postprocess_tool_call),
    "sync_vasp_output": (validate_vasp_postprocess_tool_call, execute_vasp_postprocess_tool_call),
}

_LLM_CLEANUP_INTENTS = {
    "cleanup_remote_job",
    "cleanup_all_remote_jobs",
    "cleanup_remote_vasp_job",
    "cleanup_all_remote_vasp_jobs",
}


def dispatch_classified_intent(
    tool_call: ToolCall,
    intent: str,
    *,
    state: ConversationState | None = None,
    handlers: DispatcherHandlers | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
) -> DispatchResult:
    """Route an LLM-produced ToolCall through validate → execute.

    This bypasses the rule-based ``make_*_tool_call()`` step and feeds the
    structured ``ToolCall`` directly into validation and execution.  It is
    the entry point used when the rule-based router returns ``rag_qa`` and
    the LLM classifier subsequently identifies a known intent.

    For intents that already have validate/execute functions (job_status,
    job_output, job_error, register_vasp_job, sync_vasp_output) we call
    them directly.  For all other intents we reconstruct a keyword-rich
    question and fall back to the original ``dispatch_tool_request`` path.
    """
    active_state = state or GLOBAL_CONVERSATION_STATE

    # ------------------------------------------------------------------
    # 0.  Resolve "last" / reference-style job_id → concrete number
    #     before any downstream processing, so cleanup and submit paths
    #     receive a concrete job_id they can act on.  (Bug 2 fix)
    # ------------------------------------------------------------------
    tool_call = _resolve_reference_ids(tool_call, intent, active_state)

    # ------------------------------------------------------------------
    # 1.  Clarify — the LLM decided it needs to ask the user a question
    # ------------------------------------------------------------------
    if tool_call.tool == "clarify":
        return DispatchResult(
            handled=True,
            intent=intent,
            success=False,
            message=tool_call.arguments.get("question", "能再具体描述一下吗？"),
            data={"needs_clarification": True},
            tool_result=ToolResult(
                success=False,
                message=tool_call.arguments.get("question", ""),
                tool_call=tool_call,
            ),
        )

    # ------------------------------------------------------------------
    # 2.  Direct validate → execute path (job query, VASP postprocess)
    #     execute_* internally calls validate_*, so we call execute
    #     directly and inspect the result for clarify signals.
    # ------------------------------------------------------------------
    dispatch_entry = _LLM_DISPATCH_TABLE.get(intent)

    if dispatch_entry is not None:
        _, execute_func = dispatch_entry
        active_handlers = handlers or {}

        # Allow test suites to inject custom execute funcs
        custom_execute = active_handlers.get(f"execute_{intent}")
        executor = custom_execute or execute_func
        result = executor(tool_call, state=active_state)

        if result.data.get("needs_clarification"):
            return DispatchResult(
                handled=True,
                intent=intent,
                success=False,
                message=result.message,
                data=dict(result.data),
                tool_result=result,
            )

        return DispatchResult(
            handled=True,
            intent=intent,
            success=result.success,
            message=result.message,
            data=dict(result.data),
            tool_result=result,
        )

    if intent == "generate_test_file":
        result = _execute_llm_test_tool_call(tool_call)
        return DispatchResult(
            handled=True,
            intent=intent,
            success=result.success,
            message=result.message,
            data=dict(result.data),
            tool_result=result,
        )

    if intent in _LLM_CLEANUP_INTENTS:
        cleanup_call = tool_call
        if not cleanup_call.arguments.get("original_text"):
            cleanup_args = dict(cleanup_call.arguments)
            cleanup_args["original_text"] = _reconstruct_question(cleanup_call, intent)
            cleanup_call = ToolCall(
                tool=cleanup_call.tool,
                arguments=cleanup_args,
                source=cleanup_call.source,
                confidence=cleanup_call.confidence,
                needs_confirmation=cleanup_call.needs_confirmation,
                metadata=cleanup_call.metadata,
            )
        if handlers and handlers.get("cleanup"):
            result = handlers["cleanup"](cleanup_call.arguments["original_text"], intent)
            return DispatchResult(
                handled=True,
                intent=intent,
                success=result.success,
                message=result.message,
                data=dict(result.data),
                tool_result=result,
            )
        result = execute_cleanup_prepare_tool_call(cleanup_call)
        return DispatchResult(
            handled=True,
            intent=intent,
            success=result.success,
            message=result.message,
            data=dict(result.data),
            tool_result=result,
        )

    # ------------------------------------------------------------------
    # 3.  For other intents (submit_job, cleanup_*, generate_*, etc.)
    #     reconstruct a keyword-rich question and fall back to the
    #     standard dispatch_tool_request pipeline so existing
    #     confirmation dialogs and parameter extraction still work.
    # ------------------------------------------------------------------
    if can_dispatch_intent(intent):
        enriched = _reconstruct_question(tool_call, intent)
        return dispatch_tool_request(
            enriched if enriched else tool_call.arguments.get("original_text", ""),
            intent,
            state=active_state,
            handlers=handlers,
            uploaded_files=uploaded_files,
        )

    # ------------------------------------------------------------------
    # 4.  Not in TOOL_DISPATCH_INTENTS — return handled=False so the
    #     caller can route the intent to its own handler or rag_qa.
    # ------------------------------------------------------------------
    return DispatchResult(handled=False, intent=intent)


def _resolve_reference_ids(
    tool_call: ToolCall,
    intent: str,
    state: ConversationState,
) -> ToolCall:
    """Replace reference strings ("last", "first") with concrete job IDs.

    The LLM classifier uses "last"/"first" markers when the user refers to
    a previous job without a numeric ID.  This function resolves those
    markers through ConversationState so downstream handlers (which expect
    concrete IDs) can work without modification.
    """
    args = dict(tool_call.arguments)
    job_id = args.get("job_id")

    if job_id is None or str(job_id) == "":
        return tool_call

    # already concrete (all digits or a path/selector)
    job_id_str = str(job_id)
    if job_id_str.isdigit() or job_id_str.startswith("/"):
        return tool_call

    inferred_kind = "vasp" if args.get("is_vasp") or "vasp" in intent else None
    resolved = state.resolve_job_id(job_id_str, kind=inferred_kind)

    if resolved and resolved != job_id_str:
        args["job_id"] = resolved
        return ToolCall(
            tool=tool_call.tool,
            arguments=args,
            source=tool_call.source,
            confidence=tool_call.confidence,
            needs_confirmation=tool_call.needs_confirmation,
            metadata=tool_call.metadata,
        )

    return tool_call


def _execute_llm_test_tool_call(tool_call: ToolCall) -> ToolResult:
    from modules.slurm.hpc_test_files import execute_test_job_tool_call, validate_test_tool_call

    args = dict(tool_call.arguments)
    if "kind" not in args and args.get("test_kind"):
        args["kind"] = args["test_kind"]

    normalized = validate_test_tool_call(ToolCall(
        tool=tool_call.tool,
        arguments=args,
        source=tool_call.source,
        confidence=tool_call.confidence,
        needs_confirmation=tool_call.needs_confirmation,
        metadata=tool_call.metadata,
    ))
    return execute_test_job_tool_call(
        normalized,
        user_request=args.get("original_text", ""),
    )


def _reconstruct_question(tool_call: ToolCall, intent: str) -> str:
    """Build a keyword-rich pseudo-question for the rule-based pipeline.

    The LLM has already extracted structured arguments, but some handlers
    were designed to parse natural-language text.  We reconstruct a
    keyword-dense string so ``make_*_tool_call`` functions can succeed.
    """
    args = tool_call.arguments
    parts: list[str] = []

    job_id = args.get("job_id")
    if job_id and str(job_id) != "last":
        parts.append(f"Job ID {job_id}")

    is_vasp = args.get("is_vasp") or any(kw in intent for kw in ("vasp",))

    if intent in ("submit_job", "submit_vasp_job"):
        parts.append("提交 VASP 作业到超算" if is_vasp else "提交作业到超算")
    elif intent == "generate_sbatch":
        parts.append("生成 sbatch 脚本")
    elif intent == "generate_vasp_job":
        parts.append("生成 VASP sbatch 脚本")
    elif intent == "generate_test_file":
        test_kind = args.get("test_kind") or args.get("kind") or ""
        file_name = args.get("file_name")

        if test_kind == "sleep":
            seconds = args.get("seconds")
            parts.append(f"生成 sleep {seconds} 秒测试文件" if seconds else "生成 sleep 测试文件")
        elif test_kind == "mpi_hostname":
            tasks = args.get("mpi_tasks") or args.get("tasks") or 4
            parts.append(f"生成 srun -n {tasks} hostname 测试文件")
        elif test_kind == "hostname":
            parts.append("生成 hostname 测试文件")
        else:
            parts.append("生成超算测试文件")

        if file_name:
            parts.append(f"文件名 {file_name}")
    elif intent in ("cleanup_remote_job", "cleanup_remote_vasp_job",
                    "cleanup_all_remote_jobs", "cleanup_all_remote_vasp_jobs"):
        parts.append("清理远端 VASP 作业" if is_vasp else "清理远端普通作业")
        if "all" in intent:
            parts.append("全部作业")
        selector = args.get("selector") or args.get("job_id")
        if selector and "all" not in intent:
            parts.append(f"作业 {selector}")
        scope = args.get("scope") or args.get("cleanup_scope") or ""
        if scope == "input":
            parts.append("仅清理 input 目录")
        elif scope == "output":
            parts.append("仅清理 output 目录")
    elif intent == "suggest_params":
        parts.append("参数建议 资源建议")
    elif intent == "diagnose_error":
        parts.append("error 诊断错误日志")
    elif intent == "troubleshoot_job":
        parts.append("pending 排查作业不运行")
    elif intent in ("generate_vasp_report", "analyze_vasp_job"):
        parts.append("生成 VASP 报告")
    elif intent in ("list_remote_jobs", "list_remote_vasp_jobs"):
        parts.append("列出远端作业编号")
    else:
        parts.append(intent)

    return " ".join(parts)


# Intents that the entry points handle directly (NOT in TOOL_DISPATCH_INTENTS
# but recognized by the entrypoint runtime via its own
# if-elif chains).  When the LLM classifies to one of these, we return a
# redirect-style DispatchResult so the caller can re-enter its own
# handler routing.
_NAMED_INTENTS = frozenset({
    "generate_sbatch",
    "current_config",
    "check_hpc_config",
    "test_hpc_submission",
    "generate_vasp_job",
    "generate_vasp_inputs",
    "generate_vasp_report",
    "analyze_vasp_job",
    "list_remote_jobs",
    "list_remote_vasp_jobs",
    "recent_jobs",
    "job_record_status",
    "preview_archive_job_records",
    "list_job_record_archives",
    "preview_restore_job_records",
    "job_detail",
    "list_local_vasp_jobs",
    "suggest_params",
    "diagnose_error",
    "diagnose_job",
    "troubleshoot_job",
})


def try_llm_dispatch(
    user_request: str,
    *,
    state: ConversationState | None = None,
    handlers: DispatcherHandlers | None = None,
    uploaded_files: list[dict[str, Any]] | None = None,
    skip_if_uploaded_files: bool = False,
) -> DispatchResult | None:
    """Attempt LLM-based intent classification + dispatch.

    Call this when the rule-based router returns ``rag_qa``.  Returns a
    ``DispatchResult`` on success, or ``None`` when the LLM also cannot
    classify the request (meaning the caller should fall through to
    knowledge-base Q&A).

    For intents that ``dispatch_classified_intent`` cannot handle (those
    not in ``TOOL_DISPATCH_INTENTS``), the returned ``DispatchResult``
    has ``handled=True`` with the classified intent preserved so the
    caller can re-route through its own if-elif handlers.
    """
    if skip_if_uploaded_files and uploaded_files:
        return None

    try:
        from modules.routing.intent_classifier import classify_to_tool_call
    except ImportError:
        return None

    # Quick pre-filter: skip LLM entirely for obvious chitchat / empty
    # queries.  The LLM classifier costs ~1-3 s; if the user is just
    # greeting or asking something completely unrelated, fall through to
    # the (local) rag_qa path immediately.  (Bug 4 fix)
    if _looks_like_chitchat(user_request):
        return None

    try:
        tool_call = classify_to_tool_call(
            user_request,
            context=(state or GLOBAL_CONVERSATION_STATE).context_summary(),
        )
    except Exception:
        return None

    if tool_call is None:
        return None

    intent = _intent_from_tool_call(tool_call)

    if intent == "rag_qa":
        return None

    # If the classifier produced a "clarify" tool it means the LLM needs
    # more info — pass through for the caller to display the question.
    if tool_call.tool == "clarify":
        return DispatchResult(
            handled=True,
            intent=intent,
            success=False,
            message=tool_call.arguments.get("question", "能再具体描述一下吗？"),
            data={"needs_clarification": True, "source": "llm"},
        )

    # ------------------------------------------------------------------
    # Direct validate → execute (job_query, vasp_postprocess, cleanup)
    # ------------------------------------------------------------------
    result = dispatch_classified_intent(
        tool_call,
        intent,
        state=state,
        handlers=handlers,
        uploaded_files=uploaded_files,
    )

    if result.handled:
        return result

    # ------------------------------------------------------------------
    # The intent is not in TOOL_DISPATCH_INTENTS but IS a known named
    # intent (e.g. suggest_params, diagnose_error).  Return a "redirect"
    # result so the caller can re-enter its own handler chain.
    # ------------------------------------------------------------------
    if intent in _NAMED_INTENTS:
        return DispatchResult(
            handled=True,
            intent=intent,
            success=True,
            message="",  # caller fills in via its own handler
            data={"source": "llm", "llm_redirect": True},
        )

    return None


def _looks_like_chitchat(user_request: str) -> bool:
    """Quick heuristic to avoid calling the LLM classifier on pure chitchat.

    Returns True when the input is very likely not a work-related request
    (so we can skip the API call and fall through to rag_qa).
    """
    normalized = user_request.lower().replace(" ", "")

    # Very short / greeting-only
    if len(normalized) <= 2:
        return True

    greetings = {"你好", "hello", "hi", "hey", "在吗", "在不在", "hello!", "hi!"}
    if normalized in greetings or normalized.rstrip("!！") in greetings:
        return True

    # Pure capability questions (no actual operation requested)
    pure_info = {
        "你能做什么", "你能干什么", "你会什么", "你是什么", "你是谁",
        "whatcanyoudo", "whoareyou", "whatareyou",
    }
    if normalized in pure_info:
        return True

    # Completely off-topic
    off_topic_markers = [
        "天气", "股票", "新闻", "足球", "篮球", "电影",
        "weather", "stock", "news", "今天吃",
    ]
    if any(marker in normalized for marker in off_topic_markers):
        return True

    return False


def _intent_from_tool_call(tool_call: ToolCall) -> str:
    """Infer the router intent from a ToolCall tool name."""
    tool = tool_call.tool
    tool_to_intent = {
        "query_job_status": "job_status",
        "read_job_output": "job_output",
        "read_job_error": "job_error",
        "prepare_cleanup_remote_job": "cleanup_remote_job",
        "prepare_cleanup_all_remote_jobs": "cleanup_all_remote_jobs",
        "prepare_cleanup_remote_vasp_job": "cleanup_remote_vasp_job",
        "prepare_cleanup_all_remote_vasp_jobs": "cleanup_all_remote_vasp_jobs",
        "register_vasp_job": "register_vasp_job",
        "sync_vasp_output": "sync_vasp_output",
    }
    if tool in tool_to_intent:
        return tool_to_intent[tool]

    if tool.startswith("clarify"):
        metadata = tool_call.metadata or {}
        return metadata.get("original_intent", "rag_qa")

    # For direct intent tools (generate_sbatch, suggest_params, etc.)
    known_intents = {
        "submit_job", "submit_vasp_job", "generate_sbatch",
        "current_config", "check_hpc_config", "test_hpc_submission",
        "generate_vasp_job", "generate_test_file",
        "generate_vasp_inputs", "generate_vasp_report", "analyze_vasp_job",
        "suggest_params", "diagnose_error", "troubleshoot_job",
        "diagnose_job",
        "list_remote_jobs", "list_remote_vasp_jobs",
    }
    if tool in known_intents:
        return tool

    return "rag_qa"
