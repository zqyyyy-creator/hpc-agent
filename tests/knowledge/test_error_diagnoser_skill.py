from tests import _bootstrap  # noqa: F401

import json
import tempfile
from pathlib import Path

from modules.knowledge.error_diagnoser import ErrorDiagnoser
from modules.knowledge.error_case_manager import (
    append_real_case,
    build_error_case_draft,
    load_real_cases as load_real_cases_from_path,
)
from modules.core.conversation_state import ConversationState
from modules.routing.router import detect_intent


def assert_contains(text: str, expected: str):
    if expected not in text:
        raise AssertionError(f"Expected to find {expected!r} in:\n{text}")


def assert_not_contains(text: str, unexpected: str):
    if unexpected in text:
        raise AssertionError(f"Did not expect to find {unexpected!r} in:\n{text}")


def diagnose_text(log_text: str):
    diagnoser = ErrorDiagnoser()
    return diagnoser.format_results(diagnoser.diagnose(log_text))


def load_project_real_cases():
    path = _bootstrap.PROJECT_ROOT / "data/errors/real_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_oom_log_matches_skill_output():
    log = """
    slurmstepd: error: Detected 1 oom-kill event.
    Some processes may have been killed by the cgroup out-of-memory handler.
    """
    answer = diagnose_text(log)

    assert_contains(answer, "诊断结果：")
    assert_contains(answer, "Out of Memory")
    assert_contains(answer, "类型: memory")
    assert_contains(answer, "可能原因:")
    assert_contains(answer, "解决方案:")
    assert_contains(answer, "推荐排查命令:")


def test_python_module_not_found_log():
    log = "Traceback: ModuleNotFoundError: No module named torch"
    answer = diagnose_text(log)

    assert detect_intent(log) == "diagnose_error"
    assert_contains(answer, "Module Not Found")
    assert_contains(answer, "类型: python")
    assert_contains(answer, "推荐环境修复:")
    assert_contains(answer, "which python")
    assert_not_contains(answer, "推荐 Slurm 参数/配置:")


def test_invalid_partition_does_not_invent_cluster_name():
    log = "sbatch: error: Batch job submission failed: Invalid partition name specified"
    answer = diagnose_text(log)

    assert_contains(answer, "Invalid Partition")
    assert_contains(answer, "集群相关参数:")
    assert_contains(answer, "partition/account 需要以当前超算")
    assert_not_contains(answer, "#SBATCH --partition=general")
    assert_not_contains(answer, "#SBATCH --partition=gpu")


def test_disk_quota_does_not_recommend_rm_rf():
    log = "OSError: Disk quota exceeded"
    answer = diagnose_text(log)

    assert_contains(answer, "Disk Quota Exceeded")
    assert_contains(answer, "清理建议:")
    assert_not_contains(answer, "rm -rf")


def test_unknown_log_asks_for_more_complete_logs():
    answer = diagnose_text("the program stopped and I do not know why")

    assert_contains(answer, "没有匹配到已知错误")
    assert_contains(answer, "请提供更完整的日志")


def test_real_case_missing_vasp_potcar_has_context():
    answer = diagnose_text("Missing required VASP input file: POTCAR")

    assert_contains(answer, "真实案例: VASP 缺少 POTCAR")
    assert_contains(answer, "类型: vasp")
    assert_contains(answer, "修复建议:")
    assert_contains(answer, "不会生成或回显 POTCAR")
    assert_contains(answer, "HPC_LOCAL_VASP_JOBS_INPUT_DIR")


def test_real_case_vasp_mpi_setup_failure():
    answer = diagnose_text("mpirun: command not found")

    assert_contains(answer, "真实案例: VASP MPI 环境未初始化")
    assert_contains(answer, "HPC_VASP_SETUP_COMMAND")
    assert_contains(answer, "command -v mpirun")


def test_real_case_partition_failure_precedes_generic_case():
    answer = diagnose_text("sbatch: error: Batch job submission failed: Invalid partition name specified")

    assert_contains(answer, "真实案例: Slurm partition 不存在或无权限")
    assert_contains(answer, "不要照搬其他集群的 partition 名称")
    assert_contains(answer, "Invalid Partition")


def test_real_case_ssh_key_permissions():
    answer = diagnose_text("WARNING: UNPROTECTED PRIVATE KEY FILE! Permissions 0644 are too open.")

    assert_contains(answer, "真实案例: SSH 私钥权限过宽")
    assert_contains(answer, "chmod 600")
    assert_contains(answer, "HPC_KEY_PATH")


def test_real_case_api_gateway_error():
    answer = diagnose_text("authentication_error: 401 Unauthorized invalid x-api-key")

    assert_contains(answer, "真实案例: API Key 或模型网关配置错误")
    assert_contains(answer, "PARATERA_API_KEY")
    assert_contains(answer, "HPC_CLAUDE_CODE_MODEL")


def test_real_cases_schema_is_complete():
    required_fields = {
        "id",
        "domain",
        "title",
        "severity",
        "applies_to",
        "confidence",
        "patterns",
        "evidence",
        "reason",
        "suggestions",
        "commands",
        "prevention",
    }
    allowed_severities = {"info", "warning", "error"}
    allowed_confidence = {"low", "medium", "high"}
    seen_ids = set()

    cases = load_project_real_cases()
    assert len(cases) >= 20

    for case in cases:
        missing = required_fields - set(case)
        if missing:
            raise AssertionError(f"{case.get('id', '<unknown>')} missing fields: {sorted(missing)}")

        if case["id"] in seen_ids:
            raise AssertionError(f"Duplicate real case id: {case['id']}")
        seen_ids.add(case["id"])

        if case["severity"] not in allowed_severities:
            raise AssertionError(f"{case['id']} invalid severity: {case['severity']}")
        if case["confidence"] not in allowed_confidence:
            raise AssertionError(f"{case['id']} invalid confidence: {case['confidence']}")

        for field in ["patterns", "evidence", "suggestions", "commands", "applies_to"]:
            if not isinstance(case[field], list) or not case[field]:
                raise AssertionError(f"{case['id']} field {field} must be a non-empty list")

        for field in ["domain", "title", "reason", "prevention"]:
            if not isinstance(case[field], str) or not case[field].strip():
                raise AssertionError(f"{case['id']} field {field} must be a non-empty string")


def test_new_agent_workflow_real_cases_match():
    checks = [
        ("OUTCAR not found", "真实案例: VASP 分析缺少 OUTCAR"),
        ("同步文件数: 0", "真实案例: 远端输出同步为空"),
        ("WARNING: No clipboard mechanism found, pyperclip failed", "真实案例: TUI 剪贴板不可用"),
        ("请提供 Job ID、本地输出目录名或绝对路径", "真实案例: 找不到上一个作业记录"),
    ]

    for log, expected in checks:
        assert_contains(diagnose_text(log), expected)


def test_error_case_draft_from_inline_log_uses_pending_action():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/real_cases.json"
        result = build_error_case_draft(
            "把这个错误整理成案例：CustomToolError: frobnicator failed with code 42",
            diagnoser=ErrorDiagnoser(real_cases_path=path),
            path=path,
        )

    assert result["success"]
    assert result["case"]["id"].startswith("AGENT_REAL_")
    assert result["pending_action"]["kind"] == "add_error_case"
    assert "案例草稿" in result["message"]


def test_error_case_draft_uses_previous_error_turn():
    state = ConversationState()
    state.remember_turn("user", "RuntimeError: custom previous failure")
    state.remember_turn("user", "把这个错误整理成案例")

    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/real_cases.json"
        result = build_error_case_draft(
            "把这个错误整理成案例",
            state=state,
            diagnoser=ErrorDiagnoser(real_cases_path=path),
            path=path,
        )

    assert result["success"]
    assert "custom previous failure" in result["source_log"]


def test_append_real_case_writes_valid_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/real_cases.json"
        draft = build_error_case_draft(
            "整理成案例：SomeNewError: agent failed to parse widget",
            diagnoser=ErrorDiagnoser(real_cases_path=path),
            path=path,
        )
        result = append_real_case(draft["case"], path=path)
        cases = load_real_cases_from_path(path)

    assert result["success"]
    assert cases[0]["id"] == draft["case"]["id"]
    assert cases[0]["confidence"] == "medium"


def test_error_case_draft_redacts_sensitive_values():
    fake_secret = "sk-" + "secret123456789"
    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/real_cases.json"
        result = build_error_case_draft(
            "整理成案例：RuntimeError: failed at /home/alice/project/run.py "
            f"with api_key={fake_secret} and user alice@example.com",
            diagnoser=ErrorDiagnoser(real_cases_path=path),
            path=path,
        )

    text = json.dumps(result["case"], ensure_ascii=False) + result["message"]
    assert "alice@example.com" not in text
    assert "/home/alice" not in text
    assert fake_secret not in text
    assert "<email>" in text
    assert "/home/<user>" in text
    assert "api_key=<redacted>" in text


def test_default_error_knowledge_base_uses_generic_errors_file():
    diagnoser = ErrorDiagnoser()

    assert diagnoser.db_path.name == "generic_errors.json"
    assert diagnoser.real_cases_path.name == "real_cases.json"
    assert diagnoser.error_db
    assert diagnoser.real_cases


def test_legacy_errors_db_path_is_still_supported():
    with tempfile.TemporaryDirectory() as tmpdir:
        errors_dir = Path(tmpdir)
        legacy_path = errors_dir / "errors_db.json"
        legacy_path.write_text(json.dumps([
            {
                "id": "LEGACY_001",
                "category": "legacy",
                "name": "Legacy Error",
                "patterns": ["legacy failure"],
                "reason": "legacy reason",
                "solution": "legacy solution"
            }
        ]), encoding="utf-8")

        diagnoser = ErrorDiagnoser(
            db_path=str(errors_dir / "generic_errors.json"),
            real_cases_path=str(errors_dir / "real_cases.json"),
        )
        answer = diagnoser.format_results(diagnoser.diagnose("legacy failure"))

    assert_contains(answer, "Legacy Error")


if __name__ == "__main__":
    test_oom_log_matches_skill_output()
    test_python_module_not_found_log()
    test_invalid_partition_does_not_invent_cluster_name()
    test_disk_quota_does_not_recommend_rm_rf()
    test_unknown_log_asks_for_more_complete_logs()
    test_real_case_missing_vasp_potcar_has_context()
    test_real_case_vasp_mpi_setup_failure()
    test_real_case_partition_failure_precedes_generic_case()
    test_real_case_ssh_key_permissions()
    test_real_case_api_gateway_error()
    test_real_cases_schema_is_complete()
    test_new_agent_workflow_real_cases_match()
    test_error_case_draft_from_inline_log_uses_pending_action()
    test_error_case_draft_uses_previous_error_turn()
    test_append_real_case_writes_valid_json()
    test_error_case_draft_redacts_sensitive_values()
    test_default_error_knowledge_base_uses_generic_errors_file()
    test_legacy_errors_db_path_is_still_supported()
    print("All error diagnoser skill checks passed.")
