from tests import _bootstrap  # noqa: F401
import json
from pathlib import Path

from modules.core.conversation_state import ConversationState
from modules.knowledge.knowledge_base import (
    expand_query,
    build_ask_llm_messages,
    load_documents,
    retrieve,
)


RAG_CASES_PATH = Path(globals().get("__file__", "tests/knowledge/test_knowledge_base_context.py")).resolve().parents[1] / "fixtures" / "rag_cases.json"


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


def test_build_ask_llm_messages_includes_prompt_skills():
    docs = [
        {
            "source": "vasp.txt#chunk0",
            "score": 0.8,
            "content": "INCAR 控制 VASP 计算参数。",
        }
    ]
    prompt_skills = [
        {
            "name": "vasp-style",
            "description": "VASP 回答风格",
            "triggers": ["VASP", "INCAR"],
            "body": "回答 VASP 问题时先解释关键 INCAR 参数。",
            "path": "/tmp/custom-skills/vasp-style/SKILL.md",
        }
    ]

    messages = build_ask_llm_messages("VASP INCAR 怎么设置", docs, prompt_skills=prompt_skills)
    system_content = messages[0]["content"]
    user_content = messages[1]["content"]

    assert "用户自定义只读 Skills" in user_content
    assert "vasp-style" in user_content
    assert "回答 VASP 问题时先解释关键 INCAR 参数" in user_content
    assert "不能执行命令、不能调用 Python" in system_content


def test_load_documents_preserves_document_context_in_chunks():
    docs, sources = load_documents()

    cluster_chunks = [
        doc
        for doc, source in zip(docs, sources)
        if source.startswith("cluster_sinfo_bscc_a.txt")
    ]

    if not cluster_chunks:
        raise AssertionError("Expected BSCC-A sinfo knowledge chunks to be loaded.")

    first_chunk = cluster_chunks[0]
    assert "文档标题：BSCC-A 超算 Slurm partition 与 sinfo 快照" in first_chunk
    assert "文档主题：cluster, slurm" in first_chunk
    assert "文档范围：bscc-a" in first_chunk
    assert "文档关键词：" in first_chunk


def test_retrieve_cluster_partition_snapshot():
    docs, sources = load_documents()
    results = retrieve("amd_test 能跑多久", docs, sources, top_k=3)
    result_sources = [result["source"] for result in results]

    if not any(source.startswith("cluster_sinfo_bscc_a.txt") for source in result_sources):
        raise AssertionError(f"Expected cluster_sinfo_bscc_a.txt in results, got {result_sources}")

    first_result = results[0]
    assert "keyword_score" in first_result
    assert "semantic_score" in first_result
    assert "metadata_boost" in first_result
    assert first_result["retrieval"] in {"keyword", "hybrid", "semantic"}


def test_retrieve_pending_prefers_pending_knowledge():
    docs, sources = load_documents()
    results = retrieve("作业一直 PD 不运行怎么办", docs, sources, top_k=3)
    result_sources = [result["source"] for result in results]

    if not result_sources or not result_sources[0].startswith("slurm_pending.txt"):
        raise AssertionError(f"Expected slurm_pending.txt first, got {result_sources}")


def test_query_expansion_adds_hpc_terms():
    expanded = expand_query("作业卡住了一直不开始怎么办")
    assert "pending" in expanded
    assert "squeue" in expanded


def test_rag_cases_hit_expected_sources():
    docs, sources = load_documents()
    cases = json.loads(RAG_CASES_PATH.read_text(encoding="utf-8"))

    failures = []
    for case in cases:
        results = retrieve(case["query"], docs, sources, top_k=3)
        result_sources = {result["source"].split("#", 1)[0] for result in results}
        expected_sources = set(case["expected_sources"])
        if not result_sources & expected_sources:
            failures.append({
                "query": case["query"],
                "expected": sorted(expected_sources),
                "actual": sorted(result_sources),
            })

    if failures:
        raise AssertionError(f"RAG retrieval fixture failures: {failures}")


if __name__ == "__main__":
    test_build_ask_llm_messages_includes_conversation_context()
    test_build_ask_llm_messages_includes_prompt_skills()
    test_load_documents_preserves_document_context_in_chunks()
    test_retrieve_cluster_partition_snapshot()
    test_retrieve_pending_prefers_pending_knowledge()
    test_query_expansion_adds_hpc_terms()
    test_rag_cases_hit_expected_sources()
    print("All knowledge base context checks passed.")
