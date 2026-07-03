from tests import _bootstrap  # noqa: F401

from modules.skills.skill_registry import load_skill_registry


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

    assert set(skills) == set(EXPECTED_SKILLS)

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


if __name__ == "__main__":
    test_skill_registry_loads_expected_skills()
    test_skill_registry_maps_intents()
    test_skill_handlers_are_importable()
    print("All skill registry checks passed.")
