from tests import _bootstrap  # noqa: F401

from tools.skill_eval import evaluate_cases, load_cases


def test_skill_eval_cases_route_to_expected_skills():
    report = evaluate_cases(load_cases(), execute=False)
    failures = [result for result in report["results"] if not result["ok"]]

    assert not failures, failures


def test_skill_eval_safe_cases_execute_through_skill_runtime():
    report = evaluate_cases(load_cases(), execute=True)
    failures = [result for result in report["results"] if not result["ok"]]

    assert not failures, failures


if __name__ == "__main__":
    test_skill_eval_cases_route_to_expected_skills()
    test_skill_eval_safe_cases_execute_through_skill_runtime()
    print("All skill eval checks passed.")
