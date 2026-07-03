from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILLS_DIR = PROJECT_ROOT / "skills"
VALID_SKILL_TYPES = {"tool", "prompt", "rule"}
VALID_RUNTIME_ADAPTERS = {
    "question_to_text",
    "injected_diagnoser",
    "tool_dispatch",
    "structured_result",
}


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

    def handler_module_and_attr(self) -> tuple[str, str]:
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


def load_skill(path: str | Path) -> SkillDefinition:
    skill_path = Path(path)
    markdown = skill_path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _parse_frontmatter(markdown)

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    skill_type = str(frontmatter.get("type", "")).strip()
    intents = _coerce_string_list(frontmatter.get("intents"), field_name="intents", skill_path=skill_path)
    handler = str(frontmatter.get("handler", "")).strip()
    metadata = frontmatter.get("metadata", {})
    runtime = frontmatter.get("runtime", {})

    if not name:
        raise ValueError(f"{skill_path}: missing required frontmatter field: name")
    if not description:
        raise ValueError(f"{skill_path}: missing required frontmatter field: description")
    if skill_type not in VALID_SKILL_TYPES:
        raise ValueError(f"{skill_path}: type must be one of {sorted(VALID_SKILL_TYPES)}")
    if not handler:
        raise ValueError(f"{skill_path}: missing required frontmatter field: handler")
    if not isinstance(metadata, dict):
        raise ValueError(f"{skill_path}: metadata must be a mapping")
    if not isinstance(runtime, dict):
        raise ValueError(f"{skill_path}: runtime must be a mapping")

    runtime = {str(key): str(value) for key, value in runtime.items()}
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
        metadata={str(key): str(value) for key, value in metadata.items()},
        runtime=runtime,
        body=body,
    )


class SkillRegistry:
    def __init__(self, skills_dir: str | Path = DEFAULT_SKILLS_DIR):
        self.skills_dir = Path(skills_dir)
        self._skills_by_name: dict[str, SkillDefinition] = {}
        self._skills_by_intent: dict[str, SkillDefinition] = {}

    def load(self) -> "SkillRegistry":
        skills: list[SkillDefinition] = []
        for path in sorted(self.skills_dir.glob("*/SKILL.md")):
            skills.append(load_skill(path))

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
        return self

    def all(self) -> list[SkillDefinition]:
        return list(self._skills_by_name.values())

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills_by_name.get(name)

    def get_by_intent(self, intent: str) -> SkillDefinition | None:
        return self._skills_by_intent.get(intent)

    def validate_handlers(self) -> list[dict[str, str]]:
        results = []
        for skill in self.all():
            try:
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


def load_skill_registry(skills_dir: str | Path = DEFAULT_SKILLS_DIR) -> SkillRegistry:
    return SkillRegistry(skills_dir).load()
