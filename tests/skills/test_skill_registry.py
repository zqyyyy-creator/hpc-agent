from tests import _bootstrap  # noqa: F401
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.skills.skill_registry import SkillRegistry, load_skill_registry


EXPECTED_SKILLS = {
    "diagnose-error": {
        "type": "rule",
        "intent": "diagnose_error",
        "handler": "modules.knowledge.error_diagnoser.ErrorDiagnoser",
        "adapter": "injected_diagnoser",
    },
    "generate-sbatch": {
        "type": "tool",
        "intent": "generate_sbatch",
        "handler": "modules.slurm.slurm_assistant.generate_sbatch_script",
        "adapter": "question_to_text",
    },
    "get-available-resources": {
        "type": "tool",
        "intent": "check_local_resources",
        "handler": "modules.skills.resource_detector.detect_resources_for_agent",
        "adapter": "question_to_text",
    },
    "generate-vasp-job": {
        "type": "tool",
        "intent": "generate_vasp_job",
        "handler": "modules.vasp.vasp_assistant.generate_vasp_sbatch_script",
        "adapter": "question_to_text",
    },
    "generate-vasp-inputs": {
        "type": "tool",
        "intent": "generate_vasp_inputs",
        "handler": "modules.vasp.vasp_input_generator.generate_vasp_inputs_from_potcar_request",
        "adapter": "structured_result",
    },
    "inspect-job": {
        "type": "tool",
        "intent": "job_status",
        "handler": "modules.routing.tool_dispatcher.dispatch_tool_request",
        "adapter": "tool_dispatch",
    },
    "suggest-params": {
        "type": "rule",
        "intent": "suggest_params",
        "handler": "modules.slurm.slurm_assistant.suggest_slurm_parameters",
        "adapter": "question_to_text",
    },
    "vasp-report": {
        "type": "prompt",
        "intent": "generate_vasp_report",
        "handler": "modules.vasp.claude_code_reporter.generate_report_with_claude",
        "adapter": "question_to_text",
        "runtime_handler": "modules.slurm.job_query.generate_vasp_report",
    },
}


def test_skill_registry_loads_expected_skills():
    registry = load_skill_registry()
    skills = {skill.name: skill for skill in registry.all()}

    assert set(EXPECTED_SKILLS).issubset(set(skills))

    for name, expected in EXPECTED_SKILLS.items():
        skill = skills[name]
        assert skill.type == expected["type"]
        assert expected["intent"] in skill.intents
        assert skill.handler == expected["handler"]
        assert skill.runtime["adapter"] == expected["adapter"]
        if "runtime_handler" in expected:
            assert skill.runtime["handler"] == expected["runtime_handler"]
        assert skill.description
        assert skill.path.is_file()


def test_skill_registry_maps_intents():
    registry = load_skill_registry()

    for name, expected in EXPECTED_SKILLS.items():
        skill = registry.get_by_intent(expected["intent"])
        assert skill is not None
        assert skill.name == name


def test_skill_handlers_are_importable():
    registry = load_skill_registry()
    results = registry.validate_handlers()
    failures = [result for result in results if result["ok"] != "true"]

    assert not failures, failures


def test_custom_read_only_prompt_skill_loads_without_handler():
    with TemporaryDirectory() as temp_root:
        custom_dir = Path(temp_root) / "custom-skills"
        skill_dir = custom_dir / "vasp-style"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: vasp-style
description: VASP 回答风格
type: prompt
triggers:
  - VASP
  - INCAR
risk: read_only
---
回答 VASP 问题时优先给出 INCAR 参数解释。
""",
            encoding="utf-8",
        )

        registry = SkillRegistry(custom_skills_dir=custom_dir).load()
        skill = registry.get("vasp-style")

        assert skill is not None
        assert skill.handler == ""
        assert skill.runtime == {}
        assert skill.source == "custom"
        assert skill.risk == "read_only"
        assert "VASP" in skill.triggers
        assert registry.validate_handlers()[-1]["ok"] == "true"


def test_custom_prompt_skill_matches_question_by_trigger():
    with TemporaryDirectory() as temp_root:
        custom_dir = Path(temp_root) / "custom-skills"
        skill_dir = custom_dir / "slurm-policy"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: slurm-policy
description: Slurm 队列回答规则
type: prompt
triggers: [排队, pending]
risk: read_only
---
解释排队问题时先提醒用户查看 squeue。
""",
            encoding="utf-8",
        )

        registry = SkillRegistry(custom_skills_dir=custom_dir).load()
        matched = registry.prompt_skills_for_question("作业一直排队怎么办")

        assert [skill.name for skill in matched] == ["slurm-policy"]


def test_custom_external_python_skill_loads_and_matches_question():
    with TemporaryDirectory() as temp_root:
        custom_dir = Path(temp_root) / "custom-skills"
        skill_dir = custom_dir / "quota-check"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: quota-check
description: 外部 quota 检查工具
type: tool
handler: handler.check_quota
triggers: [quota, 查配额]
risk: read_only
trusted: true
runtime:
  adapter: external_python
---
检查 quota。
""",
            encoding="utf-8",
        )
        (skill_dir / "handler.py").write_text(
            "def check_quota(context):\n"
            "    return {'success': True, 'message': 'quota ok'}\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(custom_skills_dir=custom_dir, trust_external_python=True).load()
        skill = registry.get("quota-check")
        matched = registry.external_python_skills_for_question("帮我查一下 quota")

        assert skill is not None
        assert skill.source == "custom"
        assert skill.runtime["adapter"] == "external_python"
        assert [item.name for item in matched] == ["quota-check"]
        assert registry.validate_handlers()[-1]["ok"] == "true"


def test_untrusted_custom_external_python_skill_is_skipped():
    with TemporaryDirectory() as temp_root:
        custom_dir = Path(temp_root) / "custom-skills"
        skill_dir = custom_dir / "quota-check"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: quota-check
description: 外部 quota 检查工具
type: tool
handler: handler.check_quota
triggers: [quota]
risk: read_only
runtime:
  adapter: external_python
---
检查 quota。
""",
            encoding="utf-8",
        )
        (skill_dir / "handler.py").write_text(
            "def check_quota(context):\n"
            "    return 'quota ok'\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(custom_skills_dir=custom_dir, trust_external_python=True).load()

        assert registry.get("quota-check") is None
        assert registry.skipped()[0].name == "quota-check"
        assert "trusted: true" in registry.skipped()[0].reason


def test_custom_external_python_skill_is_skipped_when_global_trust_disabled():
    with TemporaryDirectory() as temp_root:
        custom_dir = Path(temp_root) / "custom-skills"
        skill_dir = custom_dir / "quota-check"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: quota-check
description: 外部 quota 检查工具
type: tool
handler: handler.check_quota
triggers: [quota]
risk: read_only
trusted: true
runtime:
  adapter: external_python
---
检查 quota。
""",
            encoding="utf-8",
        )
        (skill_dir / "handler.py").write_text(
            "def check_quota(context):\n"
            "    return 'quota ok'\n",
            encoding="utf-8",
        )

        registry = SkillRegistry(custom_skills_dir=custom_dir, trust_external_python=False).load()

        assert registry.get("quota-check") is None
        assert registry.skipped()[0].name == "quota-check"
        assert "disabled" in registry.skipped()[0].reason


def test_custom_non_external_python_handler_is_rejected():
    with TemporaryDirectory() as temp_root:
        custom_dir = Path(temp_root) / "custom-skills"
        skill_dir = custom_dir / "external-tool"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: external-tool
description: 外部工具
type: tool
intents: [external_tool]
handler: modules.example.run
runtime:
  adapter: question_to_text
---
不应该加载为外部只读 Skill。
""",
            encoding="utf-8",
        )

        try:
            SkillRegistry(custom_skills_dir=custom_dir).load()
        except ValueError as error:
            assert "custom skills must be prompt-only" in str(error)
        else:
            raise AssertionError("Expected custom handler skill to be rejected.")


if __name__ == "__main__":
    test_skill_registry_loads_expected_skills()
    test_skill_registry_maps_intents()
    test_skill_handlers_are_importable()
    test_custom_read_only_prompt_skill_loads_without_handler()
    test_custom_prompt_skill_matches_question_by_trigger()
    test_custom_external_python_skill_loads_and_matches_question()
    test_untrusted_custom_external_python_skill_is_skipped()
    test_custom_external_python_skill_is_skipped_when_global_trust_disabled()
    test_custom_non_external_python_handler_is_rejected()
    print("All skill registry checks passed.")
