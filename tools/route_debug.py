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

from modules.routing.router import analyze_intent, analyze_plan, detect_intent, get_intent_risk, is_rule_confident  # noqa: E402
from modules.routing.tool_dispatcher import can_dispatch_intent, _intent_from_tool_call  # noqa: E402


ENTRYPOINT_INTENTS = {
    "generate_sbatch",
    "generate_vasp_job",
    "generate_vasp_report",
    "analyze_vasp_job",
    "list_remote_jobs",
    "list_remote_vasp_jobs",
    "suggest_params",
    "diagnose_error",
    "troubleshoot_job",
    "rag_qa",
    "clarify",
}


def _dispatch_path(intent: str) -> str:
    if can_dispatch_intent(intent):
        return "tool_dispatcher"

    if intent in ENTRYPOINT_INTENTS:
        return "entrypoint_handler"

    return "unknown"


def analyze_route(question: str, *, include_llm: bool = False) -> dict[str, Any]:
    decision = analyze_intent(question)
    plan = analyze_plan(question)
    rule_intent = decision.intent
    result: dict[str, Any] = {
        "question": question,
        "plan": None,
        "rule": {
            "intent": rule_intent,
            "confident": is_rule_confident(rule_intent),
            "dispatch_path": _dispatch_path(rule_intent),
            "risk": decision.risk,
            "reason": decision.reason,
            "matched_keywords": decision.matched_keywords,
            "skipped_rules": decision.skipped_rules,
            "needs_clarification": decision.needs_clarification,
            "clarification": decision.clarification,
        },
        "final": {
            "intent": rule_intent,
            "source": "rules" if rule_intent != "rag_qa" else "rag_qa",
            "dispatch_path": _dispatch_path(rule_intent),
            "risk": decision.risk,
        },
    }

    if plan is not None:
        result["plan"] = {
            "is_conditional": plan.is_conditional,
            "risk": plan.risk,
            "steps": [
                {
                    "index": step.index,
                    "text": step.text,
                    "route_text": step.route_text,
                    "intent": step.intent,
                    "risk": step.risk,
                    "condition": step.condition,
                    "needs_clarification": step.needs_clarification,
                    "clarification": step.clarification,
                }
                for step in plan.steps
            ],
        }
        result["final"] = {
            "intent": "multi_step_plan",
            "source": "rules",
            "dispatch_path": "entrypoint_handler",
            "risk": plan.risk,
        }

    if not include_llm:
        result["llm"] = {
            "enabled": False,
            "note": "Use --llm to call the LLM classifier when rule intent is rag_qa.",
        }
        return result

    result["llm"] = {"enabled": True, "attempted": False}
    if rule_intent != "rag_qa":
        result["llm"]["note"] = "Skipped because rule-based router already matched an intent."
        return result

    try:
        from modules.routing.intent_classifier import classify_to_tool_call

        tool_call = classify_to_tool_call(question)
    except Exception as exc:
        result["llm"].update({
            "attempted": True,
            "error": f"{type(exc).__name__}: {exc}",
        })
        return result

    result["llm"]["attempted"] = True
    if tool_call is None:
        result["llm"]["tool_call"] = None
        return result

    llm_intent = _intent_from_tool_call(tool_call)
    result["llm"]["tool_call"] = tool_call.to_dict()
    result["llm"]["intent"] = llm_intent
    result["llm"]["dispatch_path"] = _dispatch_path(llm_intent)
    result["final"] = {
        "intent": llm_intent,
        "source": "llm",
        "dispatch_path": _dispatch_path(llm_intent),
        "risk": get_intent_risk(llm_intent),
    }
    return result


def _print_text(report: dict[str, Any]) -> None:
    print(f"question: {report['question']}")

    if report.get("plan"):
        plan = report["plan"]
        print("plan: detected")
        print(f"plan conditional: {plan['is_conditional']}")
        print(f"plan risk: {plan['risk']}")
        for step in plan["steps"]:
            condition = f"; condition={step['condition']}" if step.get("condition") else ""
            print(
                f"plan step {step['index']}: intent={step['intent']}; "
                f"risk={step['risk']}{condition}; text={step['text']}; route_text={step['route_text']}"
            )

    rule = report["rule"]
    print(f"rule intent: {rule['intent']}")
    print(f"rule confident: {rule['confident']}")
    print(f"rule dispatch path: {rule['dispatch_path']}")
    print(f"rule risk: {rule['risk']}")
    print(f"rule reason: {rule['reason']}")
    print(f"matched keywords: {', '.join(rule['matched_keywords']) or '-'}")
    print(f"skipped rules: {', '.join(rule['skipped_rules']) or '-'}")
    if rule.get("needs_clarification"):
        print(f"clarification: {rule['clarification']}")

    llm = report["llm"]
    if not llm["enabled"]:
        print("llm: disabled")
        print(f"llm note: {llm['note']}")
    elif not llm.get("attempted"):
        print("llm: skipped")
        print(f"llm note: {llm.get('note', '')}")
    elif llm.get("error"):
        print("llm: error")
        print(f"llm error: {llm['error']}")
    elif llm.get("tool_call") is None:
        print("llm: no confident tool call")
    else:
        print(f"llm intent: {llm['intent']}")
        print(f"llm dispatch path: {llm['dispatch_path']}")
        print(f"llm tool call: {json.dumps(llm['tool_call'], ensure_ascii=False)}")

    final = report["final"]
    print(f"final intent: {final['intent']}")
    print(f"final source: {final['source']}")
    print(f"final dispatch path: {final['dispatch_path']}")
    print(f"final risk: {final['risk']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Debug how a natural-language request is routed by HPC Agent.",
    )
    parser.add_argument("question", help="Natural-language request to inspect.")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Call the LLM classifier when the rule router falls back to rag_qa.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON.",
    )
    args = parser.parse_args()

    report = analyze_route(args.question, include_llm=args.llm)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_text(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
