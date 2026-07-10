from tests import _bootstrap  # noqa: F401

import tempfile
import os
from pathlib import Path

from modules.core.confirmed_actions import execute_confirmed_action
from modules.core.conversation_state import ConversationState
from modules.knowledge.error_case_manager import load_real_cases


def test_confirmed_slurm_submit_records_job():
    state = ConversationState()
    result = execute_confirmed_action(
        "submit",
        {
            "script": "#!/bin/bash\npython train.py\n",
            "uploaded_files": [{"name": "train.py", "content": b"print('ok')\n"}],
        },
        state=state,
        executors={
            "submit": lambda script, uploaded_files=None: {
                "success": True,
                "answer": "Submitted batch job 12345",
                "job_id": "12345",
                "raw": {"remote_workdir": "/remote/job/12345"},
            },
        },
    )

    assert result.success
    assert result.message == "Submitted batch job 12345"
    assert result.data["job_id"] == "12345"
    assert state.last_job_id == "12345"
    assert state.last_remote_workdir == "/remote/job/12345"


def test_confirmed_vasp_submit_records_vasp_job():
    state = ConversationState()
    result = execute_confirmed_action(
        "submit_vasp",
        {
            "script": "#!/bin/bash\nvasp_std\n",
            "source_text": "目录名 si_static_test",
        },
        state=state,
        executors={
            "submit_vasp": lambda script, source_text, run_name=None: {
                "success": True,
                "answer": "Submitted VASP job 22334",
                "job_id": "22334",
                "raw": {"remote_workdir": "/remote/vasp/22334"},
            },
        },
    )

    assert result.success
    assert result.data["submission_kind"] == "vasp"
    assert state.last_job_id == "22334"
    assert state.last_vasp_job_id == "22334"


def test_confirmed_cleanup_returns_answer_and_targets():
    targets = [{"path": "/remote/job/12345", "kind": "dir"}]
    result = execute_confirmed_action(
        "cleanup",
        {"kind": "job", "targets": targets},
        executors={
            "cleanup": lambda targets: f"cleaned {len(targets)} target",
        },
    )

    assert result.success
    assert result.message == "cleaned 1 target"
    assert result.data["targets"] == targets
    assert result.data["cleanup_kind"] == "job"


def test_confirmed_archive_job_records_returns_archive_result():
    result = execute_confirmed_action(
        "archive_job_records",
        {"archive_job_ids": ["10001"], "keep_count": 2},
        executors={
            "archive_job_records": lambda payload: {
                "success": True,
                "message": "archived",
                "archive_path": "/tmp/archive.json",
                "archived_count": 1,
                "remaining_count": 2,
                "archived_job_ids": payload["archive_job_ids"],
            },
        },
    )

    assert result.success
    assert result.message == "archived"
    assert result.data["archive_path"] == "/tmp/archive.json"
    assert result.data["archived_count"] == 1


def test_confirmed_restore_job_records_returns_restore_result():
    result = execute_confirmed_action(
        "restore_job_records",
        {"archive_path": "/tmp/archive.json", "restore_job_ids": ["10001"]},
        executors={
            "restore_job_records": lambda payload: {
                "success": True,
                "message": "restored",
                "archive_path": payload["archive_path"],
                "restored_count": 1,
                "skipped_count": 0,
                "missing_count": 0,
                "restored_job_ids": payload["restore_job_ids"],
            },
        },
    )

    assert result.success
    assert result.message == "restored"
    assert result.data["archive_path"] == "/tmp/archive.json"
    assert result.data["restored_count"] == 1


def test_confirmed_add_error_case_writes_case():
    case = {
        "id": "AGENT_REAL_999",
        "domain": "agent",
        "title": "Agent 测试错误",
        "severity": "warning",
        "applies_to": ["agent"],
        "confidence": "medium",
        "patterns": ["AgentTestError"],
        "evidence": ["测试日志命中 AgentTestError"],
        "reason": "测试原因",
        "suggestions": ["测试建议"],
        "commands": ["查看完整日志"],
        "prevention": "测试预防",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = f"{tmpdir}/real_cases.json"
        result = execute_confirmed_action(
            "add_error_case",
            {"case": case, "path": path},
        )
        cases = load_real_cases(path)

    assert result.success
    assert result.data["case_id"] == "AGENT_REAL_999"
    assert cases[0]["title"] == "Agent 测试错误"


def test_confirmed_vasp_input_overwrite_generates_files():
    potcar = """
    TITEL = PAW_PBE Al 04Jan2001
    ENMAX = 240.000; ENMIN = 180.000
    ZVAL = 3.000
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        job_dir = Path(tmpdir) / "Al_test"
        job_dir.mkdir()
        (job_dir / "POTCAR").write_text(potcar, encoding="utf-8")
        (job_dir / "INCAR").write_text("OLD\n", encoding="utf-8")
        result = execute_confirmed_action(
            "generate_vasp_inputs_overwrite",
            {
                "job_dir": str(job_dir),
                "user_request": "帮我生成我的vasp作业Al_test的配置文件",
            },
        )
        incar = (job_dir / "INCAR").read_text(encoding="utf-8")

    assert result.success
    assert result.data["written_files"]
    assert "OLD" not in incar
    assert "SYSTEM =" in incar
    assert "ENCUT =" in incar


def test_confirmed_external_python_skill_executes_handler():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "local-file-summary"
        skill_dir.mkdir()
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(
            """---
name: local-file-summary
description: 本地目录文件统计
type: tool
handler: handler.summarize_local_files
triggers: [本地文件统计]
risk: read_only
trusted: true
runtime:
  adapter: external_python
---
统计本地目录。
""",
            encoding="utf-8",
        )
        (skill_dir / "handler.py").write_text(
            "def summarize_local_files(context):\n"
            "    return {\n"
            "        'success': True,\n"
            "        'message': 'confirmed external handler: ' + context['question'],\n"
            "        'data': {'skill_name': context['skill_name']},\n"
            "    }\n",
            encoding="utf-8",
        )

        original_trust = os.environ.get("HPC_AGENT_TRUST_EXTERNAL_PYTHON")
        try:
            os.environ["HPC_AGENT_TRUST_EXTERNAL_PYTHON"] = "true"
            result = execute_confirmed_action(
                "external_python_skill",
                {
                    "skill_name": "local-file-summary",
                    "skill_path": str(skill_path),
                    "question": "本地文件统计 /tmp",
                },
            )
        finally:
            if original_trust is None:
                os.environ.pop("HPC_AGENT_TRUST_EXTERNAL_PYTHON", None)
            else:
                os.environ["HPC_AGENT_TRUST_EXTERNAL_PYTHON"] = original_trust

    assert result.success
    assert result.message == "confirmed external handler: 本地文件统计 /tmp"
    assert result.data["skill"]["name"] == "local-file-summary"
    assert result.data["runtime"]["adapter"] == "external_python"


def test_confirmed_external_python_skill_times_out():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "slow-skill"
        skill_dir.mkdir()
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text(
            """---
name: slow-skill
description: 慢速外部 Skill
type: tool
handler: handler.run_slow
triggers: [慢速测试]
risk: read_only
trusted: true
runtime:
  adapter: external_python
  timeout_seconds: 0.2
---
测试超时。
""",
            encoding="utf-8",
        )
        (skill_dir / "handler.py").write_text(
            "import time\n\n"
            "def run_slow(context):\n"
            "    time.sleep(2)\n"
            "    return 'should not finish'\n",
            encoding="utf-8",
        )

        original_trust = os.environ.get("HPC_AGENT_TRUST_EXTERNAL_PYTHON")
        try:
            os.environ["HPC_AGENT_TRUST_EXTERNAL_PYTHON"] = "true"
            result = execute_confirmed_action(
                "external_python_skill",
                {
                    "skill_name": "slow-skill",
                    "skill_path": str(skill_path),
                    "question": "慢速测试",
                },
            )
        finally:
            if original_trust is None:
                os.environ.pop("HPC_AGENT_TRUST_EXTERNAL_PYTHON", None)
            else:
                os.environ["HPC_AGENT_TRUST_EXTERNAL_PYTHON"] = original_trust

    assert not result.success
    assert "TimeoutError" in result.message
    assert "timed out" in result.message


def test_unknown_confirmed_action_is_rejected():
    result = execute_confirmed_action("unknown", {})

    assert not result.success
    assert "不支持" in result.message


if __name__ == "__main__":
    test_confirmed_slurm_submit_records_job()
    test_confirmed_vasp_submit_records_vasp_job()
    test_confirmed_cleanup_returns_answer_and_targets()
    test_confirmed_archive_job_records_returns_archive_result()
    test_confirmed_restore_job_records_returns_restore_result()
    test_confirmed_add_error_case_writes_case()
    test_confirmed_vasp_input_overwrite_generates_files()
    test_confirmed_external_python_skill_executes_handler()
    test_confirmed_external_python_skill_times_out()
    test_unknown_confirmed_action_is_rejected()
    print("All confirmed action checks passed.")
