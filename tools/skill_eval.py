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

from modules.core.agent_runtime import execute_answer_intent  # noqa: E402
from modules.core.conversation_state import ConversationState  # noqa: E402
from modules.routing.router import analyze_intent, get_intent_risk  # noqa: E402
from modules.skills.skill_registry import load_skill_registry  # noqa: E402


DEFAULT_CASES_PATH = PROJECT_ROOT / "tests" / "fixtures" / "skill_cases.json"


class DummyDiagnoser:
    def diagnose(self, text):
        return [{"kind": "dummy", "text": text}]

    def format_results(self, results):
        return f"diagnosed: {results[0]['text']}"


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill_payload(skill) -> dict[str, Any] | None:
    if skill is None:
        return None

    return {
        "name": skill.name,
        "type": skill.type,
        "intents": list(skill.intents),
        "handler": skill.handler,
        "runtime": dict(skill.runtime),
        "path": str(skill.path),
    }


def _evaluate_execution(case: dict[str, Any], intent: str) -> dict[str, Any]:
    result = execute_answer_intent(
        case["text"],
        intent,
        documents=[],
        sources=[],
        diagnoser=DummyDiagnoser(),
        state=ConversationState(),
    )
    answer = result.answer or ""
    expected_contains = case.get("expected_answer_contains", [])
    missing = [item for item in expected_contains if item not in answer]
    ok = result.handled and not missing

    return {
        "enabled": True,
        "handled": result.handled,
        "success": result.success,
        "runtime": result.data.get("runtime"),
        "skill": result.data.get("skill"),
        "missing_answer_fragments": missing,
        "ok": ok,
    }


def evaluate_cases(cases: list[dict[str, Any]], *, execute: bool = False) -> dict[str, Any]:
    registry = load_skill_registry()
    results = []
    passed = 0

    for case in cases:
        decision = analyze_intent(case["text"])
        actual_intent = decision.intent
        skill = registry.get_by_intent(actual_intent)
        skill_payload = _skill_payload(skill)
        expected_skill = case.get("expected_skill")
        expected_adapter = case.get("expected_adapter")
        expected_runtime_handler = case.get("expected_runtime_handler")
        expected_risk = case.get("expected_risk")
        forbid_intents = set(case.get("forbid_intents", []))
        errors = []

        if actual_intent != case["expected_intent"]:
            errors.append(f"expected intent {case['expected_intent']!r}, got {actual_intent!r}")

        if actual_intent in forbid_intents:
            errors.append(f"forbidden intent was selected: {actual_intent!r}")

        actual_skill_name = skill.name if skill else None
        if actual_skill_name != expected_skill:
            errors.append(f"expected skill {expected_skill!r}, got {actual_skill_name!r}")

        actual_adapter = skill.runtime.get("adapter") if skill else None
        if expected_adapter and actual_adapter != expected_adapter:
            errors.append(f"expected adapter {expected_adapter!r}, got {actual_adapter!r}")

        actual_runtime_handler = skill.runtime.get("handler") if skill else None
        if expected_runtime_handler and actual_runtime_handler != expected_runtime_handler:
            errors.append(
                f"expected runtime handler {expected_runtime_handler!r}, got {actual_runtime_handler!r}"
            )

        actual_risk = get_intent_risk(actual_intent)
        if expected_risk and actual_risk != expected_risk:
            errors.append(f"expected risk {expected_risk!r}, got {actual_risk!r}")

        execution = {"enabled": False}
        if execute and case.get("execute") and not errors:
            execution = _evaluate_execution(case, actual_intent)
            if not execution["ok"]:
                errors.append(f"execution failed checks: {execution}")

        ok = not errors
        passed += int(ok)
        results.append({
            "text": case["text"],
            "expected_intent": case["expected_intent"],
            "actual_intent": actual_intent,
            "risk": actual_risk,
            "reason": decision.reason,
            "matched_keywords": decision.matched_keywords,
            "expected_skill": expected_skill,
            "actual_skill": skill_payload,
            "execution": execution,
            "ok": ok,
            "errors": errors,
        })

    total = len(cases)
    return {
        "execute": execute,
        "passed": passed,
        "total": total,
        "hit_rate": passed / total if total else 0.0,
        "results": results,
    }


def _print_text(report: dict[str, Any]) -> None:
    mode = "route+execute" if report["execute"] else "route"
    print(
        f"Skill eval ({mode}): {report['passed']}/{report['total']} "
        f"= {report['hit_rate']:.2%}"
    )
    for result in report["results"]:
        status = "PASS" if result["ok"] else "FAIL"
        skill_name = result["actual_skill"]["name"] if result["actual_skill"] else "-"
        adapter = (
            result["actual_skill"]["runtime"].get("adapter")
            if result["actual_skill"]
            else "-"
        )
        print()
        print(f"[{status}] {result['text']}")
        print(f"intent: expected={result['expected_intent']} actual={result['actual_intent']}")
        print(f"skill: expected={result['expected_skill']} actual={skill_name}")
        print(f"adapter: {adapter}")
        if result["errors"]:
            print("errors:")
            for error in result["errors"]:
                print(f"- {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Skill routing and runtime protocol cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--execute", action="store_true", help="Execute safe cases marked with execute=true.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = evaluate_cases(load_cases(args.cases), execute=args.execute)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)

    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
