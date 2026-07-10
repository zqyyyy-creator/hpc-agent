from __future__ import annotations

import importlib
import os
import re
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from modules.core.paths import ENV_PATH, PROJECT_ROOT, SKILLS_DIR

DEFAULT_SKILLS_DIR = SKILLS_DIR
VALID_SKILL_TYPES = {"tool", "prompt", "rule"}
VALID_RUNTIME_ADAPTERS = {
    "question_to_text",
    "injected_diagnoser",
    "tool_dispatch",
    "structured_result",
    "external_python",
}
CUSTOM_SKILLS_ENV = "HPC_AGENT_CUSTOM_SKILLS_DIR"
TRUST_EXTERNAL_PYTHON_ENV = "HPC_AGENT_TRUST_EXTERNAL_PYTHON"

load_dotenv(ENV_PATH, override=False)


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    type: str
    intents: tuple[str, ...]
    handler: str
    path: Path
    metadata: dict[str, str] = field(default_factory=dict)
    runtime: dict[str, str] = field(default_factory=dict)
    body: str = ""
    triggers: tuple[str, ...] = ()
    risk: str = ""
    source: str = "builtin"

    def handler_module_and_attr(self) -> tuple[str, str]:
        if not self.handler:
            raise ValueError(f"Skill {self.name} does not declare a Python handler.")
        if "." not in self.handler:
            raise ValueError(f"Skill {self.name} handler is not a dotted path: {self.handler}")

        module_name, attr_name = self.handler.rsplit(".", 1)
        if not module_name or not attr_name:
            raise ValueError(f"Skill {self.name} handler is not a valid dotted path: {self.handler}")

        return module_name, attr_name

    def import_handler(self):
        module_name, attr_name = self.handler_module_and_attr()
        module = importlib.import_module(module_name)
        return getattr(module, attr_name)


@dataclass(frozen=True)
class SkippedSkill:
    path: Path
    name: str
    reason: str
    source: str = "custom"


class SkillSkipped(ValueError):
    def __init__(self, path: Path, name: str, reason: str):
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.name = name
        self.reason = reason


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_frontmatter_value(value: str) -> str | list[str]:
    value = _strip_quotes(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(item.strip()) for item in inner.split(",") if item.strip()]
    return value


def _parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Skill file is missing YAML-style frontmatter.")

    end_index = None
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_index = index
            break

    if end_index is None:
        raise ValueError("Skill file frontmatter is not closed with ---.")

    frontmatter_lines = lines[1:end_index]
    body = "\n".join(lines[end_index + 1:]).strip()
    data: dict[str, Any] = {}
    current_map_key: str | None = None
    current_list_key: str | None = None

    for raw_line in frontmatter_lines:
        if not raw_line.strip():
            continue

        stripped = raw_line.strip()

        if stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError(f"List item without list key: {raw_line}")
            data.setdefault(current_list_key, []).append(_strip_quotes(stripped[2:].strip()))
            continue

        if raw_line.startswith("  ") and current_map_key:
            if ":" not in stripped:
                raise ValueError(f"Unsupported nested frontmatter line: {raw_line}")
            key, value = stripped.split(":", 1)
            data.setdefault(current_map_key, {})[key.strip()] = str(_parse_frontmatter_value(value.strip()))
            continue

        current_map_key = None
        current_list_key = None

        if ":" not in stripped:
            raise ValueError(f"Unsupported frontmatter line: {raw_line}")

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        if not value:
            if key in {"metadata", "runtime"}:
                data[key] = {}
                current_map_key = key
            else:
                data[key] = []
                current_list_key = key
            continue

        data[key] = _parse_frontmatter_value(value)

    return data, body


def _coerce_string_list(value: Any, *, field_name: str, skill_path: Path) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError(f"{skill_path}: {field_name} must be a string or list of strings.")

    cleaned = tuple(str(item).strip() for item in items if str(item).strip())
    if not cleaned:
        raise ValueError(f"{skill_path}: {field_name} must not be empty.")
    return cleaned


def _coerce_optional_string_list(value: Any, *, field_name: str, skill_path: Path) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, list) and not value:
        return ()
    return _coerce_string_list(value, field_name=field_name, skill_path=skill_path)


def _is_read_only_risk(value: str) -> bool:
    return value.strip().lower().replace("-", "_") in {"", "read_only", "readonly"}


def _is_truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _trust_external_python_from_env() -> bool:
    return _is_truthy(os.getenv(TRUST_EXTERNAL_PYTHON_ENV, ""))


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _score_prompt_skill(skill: SkillDefinition, question: str) -> int:
    question_norm = _normalize_match_text(question)
    if not question_norm:
        return 0

    score = 0
    candidates = list(skill.triggers)
    candidates.append(skill.name)

    for candidate in candidates:
        candidate_norm = _normalize_match_text(candidate)
        if len(candidate_norm) < 2:
            continue
        if candidate_norm in question_norm:
            score += 10
        elif question_norm in candidate_norm:
            score += 4

    return score


def _is_external_python_skill(skill_type: str, handler: str, runtime: dict[str, str]) -> bool:
    return skill_type == "tool" and bool(handler) and runtime.get("adapter", "").strip() == "external_python"


def _validate_external_python_handler_decl(skill_path: Path, handler: str) -> tuple[str, str]:
    if not re.fullmatch(r"handler\.[A-Za-z_][A-Za-z0-9_]*", handler):
        raise ValueError(f"{skill_path}: external_python handler must use format handler.function_name")

    module_name, function_name = handler.split(".", 1)
    return module_name, function_name


def _validate_external_python_handler_file(skill_path: Path, handler: str) -> None:
    _, function_name = _validate_external_python_handler_decl(skill_path, handler)
    handler_path = skill_path.parent / "handler.py"
    if not handler_path.is_file():
        raise ValueError(f"{skill_path}: external_python handler.py does not exist")

    tree = ast.parse(handler_path.read_text(encoding="utf-8", errors="replace"), filename=str(handler_path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return
    raise ValueError(f"{skill_path}: handler.py does not define function {function_name}")


def load_skill(
    path: str | Path,
    *,
    source: str = "builtin",
    trust_external_python: bool | None = None,
) -> SkillDefinition:
    skill_path = Path(path)
    markdown = skill_path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _parse_frontmatter(markdown)

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    skill_type = str(frontmatter.get("type", "")).strip()
    intents = _coerce_optional_string_list(frontmatter.get("intents"), field_name="intents", skill_path=skill_path)
    triggers = _coerce_optional_string_list(frontmatter.get("triggers"), field_name="triggers", skill_path=skill_path)
    handler = str(frontmatter.get("handler", "")).strip()
    metadata = frontmatter.get("metadata", {})
    runtime = frontmatter.get("runtime", {})
    risk = str(frontmatter.get("risk", "")).strip()
    trusted = _is_truthy(frontmatter.get("trusted", metadata.get("trusted") if isinstance(metadata, dict) else ""))

    if not name:
        raise ValueError(f"{skill_path}: missing required frontmatter field: name")
    if not description:
        raise ValueError(f"{skill_path}: missing required frontmatter field: description")
    if skill_type not in VALID_SKILL_TYPES:
        raise ValueError(f"{skill_path}: type must be one of {sorted(VALID_SKILL_TYPES)}")
    if not isinstance(metadata, dict):
        raise ValueError(f"{skill_path}: metadata must be a mapping")
    if not isinstance(runtime, dict):
        raise ValueError(f"{skill_path}: runtime must be a mapping")

    runtime = {str(key): str(value) for key, value in runtime.items()}
    metadata = {str(key): str(value) for key, value in metadata.items()}
    if trusted:
        metadata["trusted"] = "true"
    risk = risk or metadata.get("risk", "")

    prompt_only = skill_type == "prompt" and not handler
    external_python = source == "custom" and _is_external_python_skill(skill_type, handler, runtime)
    if source == "custom" and not (prompt_only or external_python):
        raise ValueError(
            f"{skill_path}: custom skills must be prompt-only read_only skills or external_python read_only tools."
        )
    if prompt_only:
        if not body:
            raise ValueError(f"{skill_path}: prompt-only skill must include Markdown instructions.")
        if any(str(key).strip().lower() == "handler" for key in runtime):
            raise ValueError(f"{skill_path}: prompt-only skill must not declare runtime.handler.")
        if not _is_read_only_risk(risk):
            raise ValueError(f"{skill_path}: prompt-only skill must be read_only.")
        risk = "read_only"
    elif external_python:
        trust_enabled = _trust_external_python_from_env() if trust_external_python is None else trust_external_python
        if not trust_enabled:
            raise SkillSkipped(
                skill_path,
                name,
                f"external_python disabled; set {TRUST_EXTERNAL_PYTHON_ENV}=true to enable",
            )
        if not trusted:
            raise SkillSkipped(skill_path, name, "external_python skill missing trusted: true")
        if not triggers:
            raise ValueError(f"{skill_path}: external_python skill must declare triggers.")
        if not _is_read_only_risk(risk):
            raise ValueError(f"{skill_path}: external_python skill must be read_only.")
        _validate_external_python_handler_decl(skill_path, handler)
        _validate_external_python_handler_file(skill_path, handler)
        risk = "read_only"
    else:
        if not intents:
            raise ValueError(f"{skill_path}: missing required frontmatter field: intents")
        if not handler:
            raise ValueError(f"{skill_path}: missing required frontmatter field: handler")
        adapter = runtime.get("adapter", "").strip()
        if not adapter:
            raise ValueError(f"{skill_path}: missing required runtime.adapter")
        if adapter not in VALID_RUNTIME_ADAPTERS:
            raise ValueError(
                f"{skill_path}: runtime.adapter must be one of {sorted(VALID_RUNTIME_ADAPTERS)}"
            )

    return SkillDefinition(
        name=name,
        description=description,
        type=skill_type,
        intents=intents,
        handler=handler,
        path=skill_path,
        metadata=metadata,
        runtime=runtime,
        body=body,
        triggers=triggers,
        risk=risk,
        source=source,
    )


class SkillRegistry:
    def __init__(
        self,
        skills_dir: str | Path = DEFAULT_SKILLS_DIR,
        custom_skills_dir: str | Path | None = None,
        trust_external_python: bool | None = None,
    ):
        self.skills_dir = Path(skills_dir)
        self.custom_skills_dir = Path(custom_skills_dir).expanduser() if custom_skills_dir else _custom_skills_dir_from_env()
        self.trust_external_python = (
            _trust_external_python_from_env()
            if trust_external_python is None
            else trust_external_python
        )
        self._skills_by_name: dict[str, SkillDefinition] = {}
        self._skills_by_intent: dict[str, SkillDefinition] = {}
        self._skipped_skills: list[SkippedSkill] = []

    def load(self) -> "SkillRegistry":
        skills: list[SkillDefinition] = []
        skipped_skills: list[SkippedSkill] = []
        for path in sorted(self.skills_dir.glob("*/SKILL.md")):
            skills.append(load_skill(path, source="builtin"))

        if self.custom_skills_dir and self.custom_skills_dir.is_dir():
            for path in sorted(self.custom_skills_dir.glob("*/SKILL.md")):
                try:
                    skills.append(
                        load_skill(
                            path,
                            source="custom",
                            trust_external_python=self.trust_external_python,
                        )
                    )
                except SkillSkipped as skipped:
                    skipped_skills.append(
                        SkippedSkill(
                            path=skipped.path,
                            name=skipped.name,
                            reason=skipped.reason,
                            source="custom",
                        )
                    )

        names: set[str] = set()
        intents: dict[str, str] = {}

        for skill in skills:
            if skill.name in names:
                raise ValueError(f"Duplicate skill name: {skill.name}")
            names.add(skill.name)

            for intent in skill.intents:
                if intent in intents:
                    raise ValueError(
                        f"Intent {intent!r} is registered by both {intents[intent]!r} and {skill.name!r}"
                    )
                intents[intent] = skill.name

        self._skills_by_name = {skill.name: skill for skill in skills}
        self._skills_by_intent = {
            intent: skill
            for skill in skills
            for intent in skill.intents
        }
        self._skipped_skills = skipped_skills
        return self

    def all(self) -> list[SkillDefinition]:
        return list(self._skills_by_name.values())

    def skipped(self) -> list[SkippedSkill]:
        return list(self._skipped_skills)

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills_by_name.get(name)

    def get_by_intent(self, intent: str) -> SkillDefinition | None:
        return self._skills_by_intent.get(intent)

    def prompt_skills_for_question(self, question: str, *, limit: int = 3) -> list[SkillDefinition]:
        scored: list[tuple[int, SkillDefinition]] = []
        for skill in self.all():
            if skill.type != "prompt" or skill.handler:
                continue
            if not _is_read_only_risk(skill.risk):
                continue
            score = _score_prompt_skill(skill, question)
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [skill for _, skill in scored[:limit]]

    def external_python_skills_for_question(self, question: str, *, limit: int = 1) -> list[SkillDefinition]:
        scored: list[tuple[int, SkillDefinition]] = []
        for skill in self.all():
            if skill.source != "custom":
                continue
            if skill.runtime.get("adapter") != "external_python":
                continue
            if skill.type != "tool" or not _is_read_only_risk(skill.risk):
                continue
            score = _score_prompt_skill(skill, question)
            if score > 0:
                scored.append((score, skill))

        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [skill for _, skill in scored[:limit]]

    def validate_handlers(self) -> list[dict[str, str]]:
        results = []
        for skill in self.all():
            if skill.type == "prompt" and not skill.handler:
                results.append({
                    "skill": skill.name,
                    "handler": "",
                    "ok": "true",
                    "error": "",
                })
                continue
            try:
                if skill.runtime.get("adapter") == "external_python":
                    _validate_external_python_handler_file(skill.path, skill.handler)
                else:
                    skill.import_handler()
                    runtime_handler = skill.runtime.get("handler", "")
                    if runtime_handler:
                        _import_dotted_path(runtime_handler)
            except Exception as exc:
                results.append({
                    "skill": skill.name,
                    "handler": skill.handler,
                    "ok": "false",
                    "error": f"{type(exc).__name__}: {exc}",
                })
            else:
                results.append({
                    "skill": skill.name,
                    "handler": skill.handler,
                    "ok": "true",
                    "error": "",
                })
        return results


def _import_dotted_path(dotted_path: str):
    if "." not in dotted_path:
        raise ValueError(f"Handler is not a dotted path: {dotted_path}")

    module_name, attr_name = dotted_path.rsplit(".", 1)
    if not module_name or not attr_name:
        raise ValueError(f"Handler is not a valid dotted path: {dotted_path}")

    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def _custom_skills_dir_from_env() -> Path | None:
    raw_value = os.getenv(CUSTOM_SKILLS_ENV, "").strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser()


def load_skill_registry(
    skills_dir: str | Path = DEFAULT_SKILLS_DIR,
    custom_skills_dir: str | Path | None = None,
    trust_external_python: bool | None = None,
) -> SkillRegistry:
    return SkillRegistry(
        skills_dir,
        custom_skills_dir=custom_skills_dir,
        trust_external_python=trust_external_python,
    ).load()
