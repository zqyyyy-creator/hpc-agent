from tests import _bootstrap  # noqa: F401
import json
from pathlib import Path

from modules.routing.router import analyze_intent, detect_intent, get_intent_risk


ROUTE_CASES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "route_cases.json"


def load_route_cases():
    return json.loads(ROUTE_CASES_PATH.read_text(encoding="utf-8"))


def test_route_cases_fixture_schema():
    cases = load_route_cases()

    assert cases
    seen_texts = set()
    for index, case in enumerate(cases):
        assert case.get("text"), f"case #{index} missing text"
        assert case.get("intent"), f"case #{index} missing intent"
        assert case["text"] not in seen_texts, f"duplicate route case: {case['text']}"
        seen_texts.add(case["text"])


def test_route_cases_fixture():
    for case in load_route_cases():
        actual_intent = detect_intent(case["text"])
        assert actual_intent == case["intent"], (
            f"{case['text']!r}: expected {case['intent']!r}, got {actual_intent!r}"
        )

        if case.get("risk"):
            assert get_intent_risk(actual_intent) == case["risk"], (
                f"{case['text']!r}: expected risk {case['risk']!r}, "
                f"got {get_intent_risk(actual_intent)!r}"
            )


def test_route_cases_explainable():
    for case in load_route_cases():
        decision = analyze_intent(case["text"])
        assert decision.intent == case["intent"]
        assert decision.reason
        assert decision.risk == get_intent_risk(case["intent"])


if __name__ == "__main__":
    test_route_cases_fixture_schema()
    test_route_cases_fixture()
    test_route_cases_explainable()
    print("All route case fixture checks passed.")
