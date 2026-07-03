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

from modules.knowledge.knowledge_base import load_documents, retrieve  # noqa: E402


DEFAULT_CASES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "rag_cases.json"


def _source_file(source: str) -> str:
    return source.split("#", 1)[0]


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_cases(cases: list[dict[str, Any]], *, top_k: int = 3) -> dict[str, Any]:
    documents, sources = load_documents()
    results = []
    passed = 0

    for case in cases:
        query = case["query"]
        expected_sources = set(case["expected_sources"])
        retrieved = retrieve(query, documents, sources, top_k=top_k)
        retrieved_sources = [_source_file(item["source"]) for item in retrieved]
        hit = bool(expected_sources & set(retrieved_sources))
        passed += int(hit)
        results.append({
            "query": query,
            "expected_sources": sorted(expected_sources),
            "retrieved_sources": retrieved_sources,
            "hit": hit,
            "top_results": [
                {
                    "source": item["source"],
                    "score": item.get("score", 0.0),
                    "tfidf_score": item.get("tfidf_score", 0.0),
                    "bm25_score": item.get("bm25_score", 0.0),
                    "metadata_boost": item.get("metadata_boost", 0.0),
                }
                for item in retrieved
            ],
        })

    total = len(cases)
    return {
        "top_k": top_k,
        "passed": passed,
        "total": total,
        "hit_rate": passed / total if total else 0.0,
        "results": results,
    }


def _print_text(report: dict[str, Any]) -> None:
    print(
        f"RAG eval: {report['passed']}/{report['total']} "
        f"hit@{report['top_k']} = {report['hit_rate']:.2%}"
    )
    for result in report["results"]:
        status = "PASS" if result["hit"] else "FAIL"
        print()
        print(f"[{status}] {result['query']}")
        print(f"expected: {', '.join(result['expected_sources'])}")
        print(f"retrieved: {', '.join(result['retrieved_sources']) or '-'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval against fixture cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = evaluate_cases(load_cases(args.cases), top_k=args.top_k)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)

    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
