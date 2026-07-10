from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback


def _load_handler(skill_name: str, skill_path: str, handler_decl: str):
    if not handler_decl.startswith("handler.") or handler_decl.count(".") != 1:
        raise ValueError(f"External skill {skill_name} handler must use format handler.function_name")

    _, function_name = handler_decl.split(".", 1)
    handler_path = os.path.abspath(os.path.join(os.path.dirname(skill_path), "handler.py"))
    if not os.path.isfile(handler_path):
        raise ValueError(f"External skill {skill_name} handler.py does not exist: {handler_path}")

    module_name = f"hpc_agent_external_skill_{skill_name.replace('-', '_')}_{abs(hash(handler_path))}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load external skill handler: {handler_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, function_name, None)
    if not callable(handler):
        raise ValueError(f"External skill {skill_name} handler {function_name} is not callable.")
    return handler


def run_payload(payload: dict) -> dict:
    skill = payload.get("skill") or {}
    context = payload.get("context") or {}
    handler = _load_handler(
        str(skill.get("name", "")),
        str(skill.get("path", "")),
        str(skill.get("handler", "")),
    )
    return {"ok": True, "raw_result": handler(context)}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(json.dumps({"ok": False, "error_type": "UsageError", "error": "expected payload path"}))
        return 2

    try:
        with open(args[0], "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        result = run_payload(payload)
    except BaseException as error:
        result = {
            "ok": False,
            "error_type": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(limit=8),
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
