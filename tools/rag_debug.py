#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge.knowledge_base import expand_query, load_documents, retrieve  # noqa: E402
from modules.routing.router import analyze_intent  # noqa: E402


def _compact(text: str, limit: int) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3] + "..."


def analyze_rag(question: str, *, top_k: int = 5, preview_chars: int = 300) -> dict[str, Any]:
    decision = analyze_intent(question)
    documents, sources = load_documents()
    results = retrieve(question, documents, sources, top_k=top_k)

    return {
        "question": question,
        "expanded_query": expand_query(question),
        "intent": {
            "name": decision.intent,
            "reason": decision.reason,
            "risk": decision.risk,
            "matched_keywords": decision.matched_keywords,
        },
        "chunks_loaded": len(documents),
        "results": [
            {
                "rank": index,
                "source": result["source"],
                "score": result.get("score", 0.0),
                "keyword_score": result.get("keyword_score", 0.0),
                "semantic_score": result.get("semantic_score", 0.0),
                "tfidf_score": result.get("tfidf_score", 0.0),
                "bm25_score": result.get("bm25_score", 0.0),
                "lexical_boost": result.get("lexical_boost", 0.0),
                "metadata_boost": result.get("metadata_boost", 0.0),
                "retrieval": result.get("retrieval", ""),
                "preview": _compact(result.get("content", ""), preview_chars),
            }
            for index, result in enumerate(results, 1)
        ],
    }


def _print_text(report: dict[str, Any]) -> None:
    intent = report["intent"]
    print(f"query: {report['question']}")
    if report["expanded_query"] != report["question"]:
        print(f"expanded query: {report['expanded_query']}")
    print(f"intent: {intent['name']}")
    print(f"reason: {intent['reason']}")
    print(f"risk: {intent['risk']}")
    print(f"matched keywords: {', '.join(intent['matched_keywords']) or '-'}")
    print(f"chunks loaded: {report['chunks_loaded']}")

    for result in report["results"]:
        print()
        print(f"{result['rank']}. {result['source']}")
        print(
            "   "
            f"score={result['score']:.4f} "
            f"keyword={result['keyword_score']:.4f} "
            f"semantic={result['semantic_score']:.4f} "
            f"tfidf={result['tfidf_score']:.4f} "
            f"bm25={result['bm25_score']:.4f} "
            f"lexical={result['lexical_boost']:.4f} "
            f"metadata={result['metadata_boost']:.4f} "
            f"mode={result['retrieval']}"
        )
        print(f"   preview: {result['preview']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Debug RAG retrieval sources and scores for an HPC Agent question.",
    )
    parser.add_argument("question", help="Question to inspect.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to show.")
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=300,
        help="Maximum preview characters for each chunk.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    report = analyze_rag(
        args.question,
        top_k=args.top_k,
        preview_chars=args.preview_chars,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
