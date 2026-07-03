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

from modules.skills.skill_registry import SkillDefinition, load_skill_registry  # noqa: E402
from modules.routing.router import analyze_intent  # noqa: E402


def _skill_to_dict(skill: SkillDefinition, *, validate_handler: bool = False) -> dict[str, Any]:
    result = {
        "name": skill.name,
        "type": skill.type,
        "description": skill.description,
        "intents": list(skill.intents),
        "handler": skill.handler,
        "runtime": skill.runtime,
        "path": str(skill.path),
        "metadata": skill.metadata,
    }

    if validate_handler:
        try:
            skill.import_handler()
        except Exception as exc:
            result["handler_ok"] = False
            result["handler_error"] = f"{type(exc).__name__}: {exc}"
        else:
            result["handler_ok"] = True
            result["handler_error"] = ""

    return result


def _print_skill(skill: SkillDefinition, *, validate_handler: bool = False) -> None:
    data = _skill_to_dict(skill, validate_handler=validate_handler)
    print(f"skill: {data['name']}")
    print(f"type: {data['type']}")
    print(f"description: {data['description']}")
    print(f"intents: {', '.join(data['intents'])}")
    print(f"handler: {data['handler']}")
    if data["runtime"]:
        runtime = ", ".join(f"{key}={value}" for key, value in data["runtime"].items())
        print(f"runtime: {runtime}")
    print(f"path: {data['path']}")
    if data["metadata"]:
        metadata = ", ".join(f"{key}={value}" for key, value in data["metadata"].items())
        print(f"metadata: {metadata}")
    if validate_handler:
        print(f"handler import: {'ok' if data['handler_ok'] else 'failed'}")
        if data["handler_error"]:
            print(f"handler error: {data['handler_error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect HPC Agent skill registry entries.")
    parser.add_argument("skill", nargs="?", help="Skill name to inspect, such as generate-sbatch.")
    parser.add_argument("--intent", help="Find the skill registered for an intent.")
    parser.add_argument("--route", help="Route a natural-language request and show the matched skill.")
    parser.add_argument("--validate", action="store_true", help="Validate handler imports.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    registry = load_skill_registry()

    if args.route:
        decision = analyze_intent(args.route)
        skill = registry.get_by_intent(decision.intent)
        route_result = {
            "question": args.route,
            "intent": decision.intent,
            "reason": decision.reason,
            "matched_keywords": decision.matched_keywords,
            "skill": _skill_to_dict(skill, validate_handler=args.validate) if skill else None,
        }
        if args.json:
            print(json.dumps(route_result, ensure_ascii=False, indent=2))
        else:
            print(f"question: {route_result['question']}")
            print(f"intent: {route_result['intent']}")
            print(f"reason: {route_result['reason']}")
            print(f"matched keywords: {', '.join(route_result['matched_keywords']) or '-'}")
            if skill:
                print()
                _print_skill(skill, validate_handler=args.validate)
            else:
                print("skill: -")
        return 0 if skill else 1

    if args.intent:
        skill = registry.get_by_intent(args.intent)
        if skill is None:
            print(f"No skill registered for intent: {args.intent}", file=sys.stderr)
            return 1
        skills = [skill]
    elif args.skill:
        skill = registry.get(args.skill)
        if skill is None:
            print(f"No skill registered with name: {args.skill}", file=sys.stderr)
            return 1
        skills = [skill]
    else:
        skills = registry.all()

    if args.json:
        print(json.dumps(
            [_skill_to_dict(skill, validate_handler=args.validate) for skill in skills],
            ensure_ascii=False,
            indent=2,
        ))
    else:
        for index, skill in enumerate(skills):
            if index:
                print()
            _print_skill(skill, validate_handler=args.validate)

    if args.validate:
        failures = [
            skill
            for skill in skills
            if not _skill_to_dict(skill, validate_handler=True).get("handler_ok")
        ]
        return 1 if failures else 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
