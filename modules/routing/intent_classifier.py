"""LLM-based intent classifier for HPC Agent.

Falls back to LLM classification when rule-based keyword matching in
router.py cannot determine the user's intent with confidence.  The
classifier returns a structured ClassifiedIntent that maps directly to
the existing ToolCall / dispatch pipeline — no text-parse-roundtrip.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from modules.core.paths import ENV_PATH
from modules.core.tool_calling import ToolCall

load_dotenv(ENV_PATH)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClassifiedIntent:
    """Result of LLM intent classification + slot-filling."""

    intent: str
    confidence: float
    arguments: dict[str, Any] = field(default_factory=dict)
    needs_clarify: bool = False
    clarify_question: str | None = None
    reasoning: str = ""

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.6 and self.intent != "rag_qa"


# ---------------------------------------------------------------------------
# Intent catalogue used by the fallback LLM classifier.
# ---------------------------------------------------------------------------

INTENT_CATALOGUE = {
    "submit_job": "提交普通作业到超算运行。关键词：帮我跑、提交到超算、submit、run on HPC。用户提到具体的 .py/.sh 文件路径+运行意图时，一般为 submit_job。",
    "submit_vasp_job": "提交 VASP 计算作业到超算。VASP 关键词（vasp/INCAR/POSCAR/DFT/结构优化/弛豫/能带/态密度/第一性原理/赝势/自洽/材料计算）+ 提交/运行意图。",
    "current_config": "查看当前 Agent 主体模型、VASP 报告模型、LLM 网关和超算目录配置。",
    "check_hpc_config": "检查超算/HPC 配置是否可用，包括本地目录、SSH key、远端工作目录等。",
    "test_hpc_submission": "一键测试超算普通 Slurm 提交流程，生成一个安全 hostname 测试作业提交预览，需要用户确认后才提交。",
    "generate_vasp_job": "生成 VASP sbatch 脚本但不提交。VASP 关键词 + 生成/写脚本/预览意图。",
    "generate_vasp_inputs": "根据本地 VASP 作业目录中已有 POTCAR 生成 INCAR/KPOINTS/POSCAR 配置文件。关键词：配置文件、输入文件、根据 POTCAR 生成、INCAR/POSCAR/KPOINTS。",
    "register_vasp_job": "登记已有的 VASP 作业，建立 Job ID 到远端目录的映射。",
    "sync_vasp_output": "从远端 HPC 同步 VASP 输出文件到本地。关键词：同步+输出/结果、拉取、下载、拿回、取回。",
    "generate_vasp_report": "调用 Claude Code 生成 VASP 分析报告/论文报告。关键词：生成报告、论文报告、methods、写报告。",
    "analyze_vasp_job": "一键分析 VASP 作业：先同步远段输出，再调用 Claude Code 生成报告。关键词：一键分析、完整分析、自动分析、analyze vasp。",
    "job_status": "查询作业是否在 squeue 中、运行状态、是否完成。关键词：查看状态、squeue、算完没、跑完没、还在跑吗、进度、怎么样、什么情况、啥情况、啥状态。",
    "job_output": "查看作业的标准输出/运行结果。关键词：读取输出、查看输出、结果、stdout、看看输出、输出什么。",
    "job_error": "查看作业的错误日志/stderr。关键词：错误日志、stderr、报错日志、失败日志。",
    "recent_jobs": "查看本地 job_registry.json 中最近记录的作业。关键词：查看最近作业、列出最近作业、我的最近作业。",
    "job_record_status": "查看本地 job_registry.json 的统计状态。关键词：查看本地作业记录状态、本地记录有多少作业、job registry 状态。",
    "preview_archive_job_records": "预览归档本地作业记录，只生成将保留/将归档的清单，不修改文件。关键词：预览归档本地作业记录、只保留最近 N 个。",
    "list_job_record_archives": "列出本地作业记录归档文件。关键词：查看本地作业记录归档、列出归档文件。",
    "preview_restore_job_records": "预览恢复本地作业记录归档，只生成将恢复/跳过清单，不修改文件。关键词：预览恢复本地作业记录归档、恢复最近一次归档。",
    "job_detail": "查看本地记录的单个作业详情和生命周期线索。关键词：查看作业详情、作业详情、详细信息，需要 job_id 或 last 引用；缺少时应反问。",
    "list_local_vasp_jobs": "列出本地 job_registry.json 中已记录的 VASP 作业。关键词：列出 VASP 作业、我的 VASP 作业、本地 VASP 作业。不要和远端 VASP 目录列表混淆。",
    "diagnose_job": "诊断指定 Job ID 的作业失败/异常原因。关键词：诊断作业、排查作业、分析作业失败，需要 job_id 或 last 引用。",
    "list_remote_jobs": "列出远端 hpc-agent-jobs 目录下的所有作业编号。",
    "list_remote_vasp_jobs": "列出远端 VASP input/output 目录下的所有作业。",
    "cleanup_remote_job": "按 Job ID 清理远端普通作业文件。关键词：清理/删除/移除 + Job ID。",
    "cleanup_all_remote_jobs": "一键清理远端全部普通作业文件。关键词：清理全部、清空全部、清理所有。",
    "cleanup_remote_vasp_job": "清理特定 VASP 作业的远端 input/output 目录。VASP + 清理/删除。",
    "cleanup_all_remote_vasp_jobs": "一键清理远端全部 VASP 作业目录。VASP + 清理全部。",
    "generate_sbatch": "生成 Slurm sbatch 脚本但不提交。关键词：生成脚本、写sbatch、预览脚本。",
    "generate_test_file": "生成 HPC 测试文件。关键词：生成测试、写个test、创建测试脚本。支持的测试类型：sleep N秒、hostname、srun hostname。",
    "suggest_params": "建议 Slurm 资源参数。关键词：多少核、多少内存、需要几个节点、cpus-per-task、申请多久、跑多久。",
    "diagnose_error": "诊断粘贴的错误日志。用户粘贴了 error/traceback/OOM/permission denied 等内容。",
    "troubleshoot_job": "排查作业 Pending/卡住/不运行的原因。关键词：一直pending、卡住、排队很久、为什么不跑、没反应、不开始。",
    "rag_qa": "通用 Slurm/HPC 知识库问答，或以上意图都不匹配时的兜底。",
}

# Mapping from catalogue intent → job_query tool name
INTENT_TO_TOOL = {
    "job_status": "query_job_status",
    "job_output": "read_job_output",
    "job_error": "read_job_error",
    "cleanup_remote_job": "prepare_cleanup_remote_job",
    "cleanup_all_remote_jobs": "prepare_cleanup_all_remote_jobs",
    "cleanup_remote_vasp_job": "prepare_cleanup_remote_vasp_job",
    "cleanup_all_remote_vasp_jobs": "prepare_cleanup_all_remote_vasp_jobs",
    "register_vasp_job": "register_vasp_job",
    "sync_vasp_output": "sync_vasp_output",
}

SYSTEM_PROMPT = """你是 HPC Agent 的意图分类器。你的任务是分析用户的自然语言请求，将它分类为已知意图，并提取结构化参数。

## 意图目录

""" + "\n".join(f"- **{k}**: {v}" for k, v in INTENT_CATALOGUE.items()) + """

## 输出格式

严格按照以下 JSON 格式输出，不要输出 Markdown 代码块，不要有任何额外解释文字：

{
  "intent": "<上述意图之一>",
  "confidence": 0.0-1.0,
  "arguments": {
    "job_id": "string|null, 作业ID数字",
    "reference": "string|null, 引用类型: 'last', 'first', 'second', null",
    "is_vasp": "boolean, 是否VASP相关",
    "query_type": "string|null, 查询类型: 'status'|'output'|'error'",
    "cleanup_scope": "string|null, 'single'|'all'|'input'|'output'|'both'",
    "test_kind": "string|null, 'sleep'|'hostname'|'mpi_hostname'",
    "seconds": "integer|null, sleep 测试的秒数",
    "mpi_tasks": "integer|null, MPI hostname 测试的进程数",
    "file_name": "string|null, 测试文件名，仅允许普通文件名",
    "selector": "string|null, VASP 作业选择的目录名/子目录名"
  },
  "needs_clarify": false,
  "clarify_question": null,
  "reasoning": "简短推理"
}

## 关键判断规则

1. **引用消解**：用户说"刚才/上次/上一个/最近/它/这个作业/那个作业"时，reference 填 "last"，不要猜测 job_id。
2. **序数引用**：用户说"第一个/第二个/前一个"时，reference 填 "first"/"second"/"previous"。
3. **VASP 检测**：出现 vasp/INCAR/POSCAR/POTCAR/KPOINTS/OUTCAR/DFT/结构优化/弛豫/能带/态密度/第一性原理/赝势/自洽/材料计算/静态计算 任一词即为 VASP 相关，设置 is_vasp=true。
4. **综合判断**：
   - "怎么样了/啥情况/有结果没/跑完没" → query_type="status"
   - "看看输出/结果是什么/输出啥内容" → query_type="output"
   - 同时包含"状态/结果"询问时，优先 query_type="status"
5. **清理范围**：出现"全部/所有/一键/清空"→ cleanup_scope="all"；"仅input/只input/输入目录"→ cleanup_scope="input"；"仅output/只output/输出目录"→ cleanup_scope="output"；默认 → cleanup_scope="both"。
6. **测试文件**：用户要求生成测试文件时，识别 test_kind（sleep/hostname/mpi_hostname）。sleep 必须提取 seconds；"一分半钟"=90，"两分钟"=120。mpi_hostname 提取 mpi_tasks，未说明时用 4。
7. **信息不足**：当意图明确但缺少关键参数时（如查询作业但无法确定 job_id 且无引用），设置 needs_clarify=true 并生成一个简短的反问。
8. **长命令分析**：如果一句话包含多个意图（如"先看看上次的VASP跑完了没，跑完了帮我生成报告"），优先识别最核心的查询/状态意图。
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    """Best-effort JSON extraction from LLM output."""
    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON block from markdown fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Extract first {...} object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def _get_llm_client():
    """Lazy-import the LLM client to avoid circular imports at module level."""
    from modules.knowledge.knowledge_base import client

    return client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(
    question: str,
    *,
    context: str = "",
    model: str | None = None,
) -> ClassifiedIntent:
    """Use the LLM to classify user input into an intent + extracted arguments.

    Parameters
    ----------
    question : str
        The user's natural-language request.
    context : str
        Optional session context summary (e.g. from
        ``ConversationState.context_summary()``).
    model : str | None
        Override the model.  Defaults to the PARATERA_MODEL env var.

    Returns
    -------
    ClassifiedIntent
    """
    llm_client = _get_llm_client()
    model_name = model or os.getenv("PARATERA_MODEL", "DeepSeek-V4-Pro")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    if context:
        messages.append({
            "role": "system",
            "content": f"当前 HPC Agent 会话上下文:\n\n{context}",
        })

    messages.append({"role": "user", "content": question})

    try:
        response = llm_client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=500,
            temperature=0.0,
            stream=False,
            timeout=20,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM intent classification failed: %s", exc)
        return ClassifiedIntent(
            intent="rag_qa",
            confidence=0.0,
            reasoning=f"LLM call failed: {exc}",
        )

    data = _extract_json(raw)

    if not data:
        logger.warning("Could not parse LLM classifier output: %s", raw[:200])
        return ClassifiedIntent(
            intent="rag_qa",
            confidence=0.0,
            reasoning="JSON parse failed",
        )

    return ClassifiedIntent(
        intent=data.get("intent", "rag_qa"),
        confidence=float(data.get("confidence", 0.5)),
        arguments=data.get("arguments", {}),
        needs_clarify=bool(data.get("needs_clarify", False)),
        clarify_question=data.get("clarify_question"),
        reasoning=data.get("reasoning", ""),
    )


def classify_to_tool_call(
    question: str,
    *,
    context: str = "",
    model: str | None = None,
) -> ToolCall | None:
    """Convenience: classify and produce a ToolCall ready for dispatch.

    Returns None when the result is rag_qa or confidence is too low,
    signaling the caller to fall back to knowledge-base Q&A.
    """
    classified = classify_intent(question, context=context, model=model)

    if not classified.is_confident:
        return None

    if classified.needs_clarify:
        return ToolCall(
            tool="clarify",
            arguments={
                "question": classified.clarify_question or "能再具体描述一下吗？",
            },
            source="llm",
            confidence=classified.confidence,
            metadata={"original_intent": classified.intent},
        )

    return _build_tool_call(classified, question)


def _build_tool_call(classified: ClassifiedIntent, question: str = "") -> ToolCall:
    """Map a ClassifiedIntent to a concrete ToolCall for the dispatch pipeline."""
    intent = classified.intent
    args = classified.arguments

    # If the intent maps directly to a job_query / cleanup / vasp tool
    tool_name = INTENT_TO_TOOL.get(intent)

    if tool_name is not None:
        # Build arguments — keep LLM-extracted values but resolve references
        # to "last" markers that the validate layer understands.
        call_args: dict[str, Any] = {"original_text": question}

        job_id = args.get("job_id")
        reference = args.get("reference")

        if job_id:
            call_args["job_id"] = str(job_id)
        elif reference:
            # The validate layer in job_query.py recognizes "last" / "first" strings
            call_args["job_id"] = reference

        if intent in {"job_status", "job_output", "job_error"} and args.get("is_vasp"):
            call_args["is_vasp"] = True

        if intent.startswith("cleanup"):
            if args.get("cleanup_scope"):
                call_args["scope"] = args["cleanup_scope"]
            if args.get("selector"):
                call_args["selector"] = args["selector"]
            elif job_id:
                call_args["job_id"] = str(job_id)

        if intent == "register_vasp_job" and args.get("selector"):
            call_args["selector"] = args["selector"]

        if intent == "sync_vasp_output":
            call_args["job_id"] = job_id or reference or ""
            if args.get("selector"):
                call_args["selector"] = args["selector"]

        return ToolCall(
            tool=tool_name,
            arguments=call_args,
            source="llm",
            confidence=classified.confidence,
            needs_confirmation=intent.startswith("cleanup"),
        )

    # For intents that don't go through the ToolCall pipeline (they are
    # dispatched directly by the entry points), return a lightweight ToolCall
    # that carries the intent and arguments.
    return ToolCall(
        tool=intent,
        arguments={
            "original_text": question,
            "job_id": args.get("job_id") or args.get("reference") or "",
            "is_vasp": args.get("is_vasp", False),
            **{k: v for k, v in args.items()
               if k not in ("job_id", "reference", "is_vasp")},
        },
        source="llm",
        confidence=classified.confidence,
    )
