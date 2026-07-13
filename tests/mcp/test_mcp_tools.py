from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.mcp import audit, prompts, resources
from modules.core.tool_calling import ToolCall, ToolResult
from modules.mcp import formatters, tools


os.environ.setdefault("HPC_AGENT_MCP_AUDIT_LOG", "/tmp/hpc-agent-test-mcp-audit.jsonl")


def test_generate_sbatch_returns_preview_only():
    def fake_prepare_submit_script(request: str):
        return {
            "ready": True,
            "message": "preview",
            "script": "#!/bin/bash\nsrun hostname",
            "tool_call": {"tool": "prepare_slurm_job", "arguments": {"user_request": request}},
        }

    with patch.object(tools, "prepare_submit_script", fake_prepare_submit_script):
        result = tools.generate_sbatch("run hostname")

    assert result["ok"] is True
    assert result["risk"] == "write_preview"
    assert result["requires_confirmation"] is False
    assert result["script"].startswith("#!/bin/bash")
    assert "不提交" in result["note"]


def test_generate_sbatch_accepts_structured_mcp_request():
    result = tools.generate_sbatch(
        """使用 HPC Agent 生成 Slurm 脚本预览:
command: hostname
nodes: 1
time: 00:05:00
partition: amd_test
"""
    )

    assert result["ok"] is True
    assert result["ready"] is True
    assert "#SBATCH --nodes=1" in result["script"]
    assert "#SBATCH --time=00:05:00" in result["script"]
    assert "#SBATCH --partition=amd_test" in result["script"]
    assert "\nhostname\n" in result["script"]
    assert result["tool_call"]["arguments"]["command"] == "hostname"
    assert result["tool_call"]["arguments"]["nodes"] == 1


def test_generate_sbatch_structured_returns_stable_preview():
    result = tools.generate_sbatch_structured(
        command="hostname",
        nodes=1,
        time_limit="00:05:00",
        partition="amd_test",
        cpus_per_task=1,
        job_name="hostname_test",
    )

    assert result["ok"] is True
    assert result["risk"] == "write_preview"
    assert result["schema_version"]
    assert result["plain_text"]
    assert result["reply"]
    assert result["requires_confirmation"] is False
    assert "#SBATCH --job-name=hostname_test" in result["script"]
    assert "#SBATCH --nodes=1" in result["script"]
    assert "#SBATCH --partition=amd_test" in result["script"]
    assert "\nhostname\n" in result["script"]
    assert result["structured_arguments"]["command"] == "hostname"
    assert result["data"]["structured_arguments"]["time_limit"] == "00:05:00"


def test_agent_chat_routes_natural_language_sbatch_preview():
    result = tools.agent_chat(
        "生成 Slurm 脚本预览：command: hostname nodes: 1 time: 00:05:00 partition: amd_test"
    )

    assert result["ok"] is True
    assert result["intent"] == "generate_sbatch"
    assert "#SBATCH --nodes=1" in result["message"]
    assert "#SBATCH --partition=amd_test" in result["message"]
    assert "\nhostname\n" in result["message"]


def test_agent_chat_keeps_pending_submission_and_requires_confirm():
    tools.GLOBAL_CONVERSATION_STATE.clear_context()
    try:
        preview = tools.agent_chat("帮我提交一个普通 Slurm 作业运行 hostname，1 核，5 分钟")

        assert preview["ok"] is True
        assert preview["intent"] == "submit_job"
        assert preview["pending_submission"]["kind"] == "slurm"
        assert preview["requires_confirmation"] is True

        blocked = tools.agent_chat("提交刚才那个")

        assert blocked["ok"] is False
        assert blocked["intent"] == "submit_pending_job"
        assert blocked["requires_confirmation"] is True
        assert blocked["pending_submission"]["script"].startswith("#!/bin/bash")
    finally:
        tools.GLOBAL_CONVERSATION_STATE.clear_context()


def test_agent_chat_submits_pending_submission_with_confirm():
    tools.GLOBAL_CONVERSATION_STATE.clear_context()
    try:
        tools.agent_chat("帮我提交一个普通 Slurm 作业运行 hostname，1 核，5 分钟")

        with patch.object(
            tools,
            "submit_prepared_job",
            return_value={
                "ok": True,
                "risk": "write_execute",
                "message": "Submitted batch job 12345",
                "data": {"job_id": "12345"},
            },
        ) as submit:
            result = tools.agent_chat("确认提交", confirm=True)

        assert result["ok"] is True
        assert result["intent"] == "submit_pending_job"
        assert result["pending_submission"] is None
        assert "Submitted batch job 12345" in result["message"]
        submit.assert_called_once()
    finally:
        tools.GLOBAL_CONVERSATION_STATE.clear_context()


def test_query_job_wraps_tool_result():
    def fake_handle_job_query_request(question, intent, state=None):
        return ToolResult(
            success=True,
            message="RUNNING",
            data={"job_id": "12345", "query_tool": "query_job_status"},
            tool_call=ToolCall(tool="query_job_status", arguments={"job_id": "12345"}),
        )

    with patch.object(tools, "handle_job_query_request", fake_handle_job_query_request):
        result = tools.query_job("12345", "status")

    assert result["ok"] is True
    assert result["message"] == "RUNNING"
    assert result["job_id"] == "12345"
    assert result["query_type"] == "status"
    assert result["data"]["query_tool"] == "query_job_status"


def test_query_job_structured_preserves_arguments():
    def fake_handle_job_query_request(question, intent, state=None):
        return ToolResult(
            success=True,
            message="RUNNING",
            data={"job_id": "12345", "query_tool": "query_job_status"},
            tool_call=ToolCall(tool="query_job_status", arguments={"job_id": "12345"}),
        )

    with patch.object(tools, "handle_job_query_request", fake_handle_job_query_request):
        result = tools.query_job_structured("12345", "status")

    assert result["ok"] is True
    assert result["structured_arguments"] == {"job_id": "12345", "query_type": "status"}
    assert result["data"]["structured_arguments"]["job_id"] == "12345"


def test_scrub_secrets_masks_sensitive_keys():
    data = {
        "PARATERA_API_KEY": "secret-value",
        "nested": {"repo_token": "token-value", "visible": "ok"},
    }

    assert formatters.scrub_secrets(data) == {
        "PARATERA_API_KEY": "***",
        "nested": {"repo_token": "***", "visible": "ok"},
    }


def test_text_payload_has_stable_response_envelope():
    result = formatters.text_payload("hello", ok=True, risk="read_only", value=1)

    assert result["ok"] is True
    assert result["risk"] == "read_only"
    assert result["message"] == "hello"
    assert result["reply"] == "hello"
    assert result["plain_text"] == "hello"
    assert result["schema_version"]
    assert result["requires_confirmation"] is False
    assert result["value"] == 1
    assert result["data"]["value"] == 1


def test_prepare_vasp_job_returns_preview_only():
    def fake_prepare_vasp_submit_script(request: str):
        return {
            "ready": True,
            "message": "vasp preview",
            "script": "#!/bin/bash\nvasp_std",
            "local_jobs_dir": "/tmp/vasp-input",
            "remote_input_dir": "/remote/input",
            "remote_output_dir": "/remote/output",
            "tool_call": {"tool": "prepare_vasp_job", "arguments": {"user_request": request}},
        }

    with patch.object(tools, "prepare_vasp_submit_script", fake_prepare_vasp_submit_script):
        result = tools.prepare_vasp_job("prepare vasp job")

    assert result["ok"] is True
    assert result["risk"] == "write_preview"
    assert result["requires_confirmation"] is False
    assert result["script"].startswith("#!/bin/bash")
    assert "不提交" in result["note"]


def test_prepare_vasp_job_structured_returns_preview_only():
    def fake_prepare_vasp_submit_script(request: str):
        assert "本地 VASP 输入目录: /tmp/vasp-input/si" in request
        assert "partition: amd_test" in request
        return {
            "ready": True,
            "message": "vasp preview",
            "script": "#!/bin/bash\nvasp_std",
            "local_jobs_dir": "/tmp/vasp-input",
            "remote_input_dir": "/remote/input",
            "remote_output_dir": "/remote/output",
            "tool_call": {"tool": "prepare_vasp_job", "arguments": {"user_request": request}},
        }

    with patch.object(tools, "prepare_vasp_submit_script", fake_prepare_vasp_submit_script):
        result = tools.prepare_vasp_job_structured(
            local_input_dir="/tmp/vasp-input/si",
            partition="amd_test",
            nodes=1,
            time_limit="00:30:00",
            job_name="si_static",
        )

    assert result["ok"] is True
    assert result["risk"] == "write_preview"
    assert result["structured_arguments"]["local_input_dir"] == "/tmp/vasp-input/si"
    assert result["data"]["structured_arguments"]["time_limit"] == "00:30:00"


def test_generate_vasp_inputs_wraps_result():
    def fake_generate(request: str, **kwargs):
        return {
            "success": True,
            "message": "generated",
            "job_dir": "/tmp/vasp-job",
            "written_files": ["/tmp/vasp-job/INCAR"],
            "jobs_dir": kwargs.get("jobs_dir"),
        }

    with patch.object(tools, "generate_vasp_inputs_from_potcar_request", fake_generate):
        result = tools.generate_vasp_inputs("generate inputs", jobs_dir="/tmp/root")

    assert result["ok"] is True
    assert result["risk"] == "write_local"
    assert result["message"] == "generated"
    assert result["job_dir"] == "/tmp/vasp-job"
    assert result["jobs_dir"] == "/tmp/root"


def test_generate_vasp_inputs_structured_wraps_result():
    def fake_generate(request: str, **kwargs):
        assert "job_name: si_static" in request
        assert "ENCUT: 400" in request
        assert "KPOINTS: 2 2 2" in request
        return {
            "success": True,
            "message": "generated",
            "job_dir": "/tmp/vasp-job",
            "written_files": ["/tmp/vasp-job/INCAR"],
            "jobs_dir": kwargs.get("jobs_dir"),
        }

    with patch.object(tools, "generate_vasp_inputs_from_potcar_request", fake_generate):
        result = tools.generate_vasp_inputs_structured(
            job_name="si_static",
            element="Si",
            calculation_type="static",
            encut=400,
            kpoints=[2, 2, 2],
            jobs_dir="/tmp/root",
        )

    assert result["ok"] is True
    assert result["risk"] == "write_local"
    assert result["structured_arguments"]["job_name"] == "si_static"
    assert result["data"]["structured_arguments"]["kpoints"] == [2, 2, 2]


def test_analyze_vasp_local_result_wraps_context():
    def fake_generate_context(local_job_dir: str):
        local_job_dir = str(local_job_dir)
        return {
            "success": True,
            "local_job_dir": local_job_dir,
            "analysis_dir": f"{local_job_dir}/analysis",
            "report_context_path": f"{local_job_dir}/analysis/report_context.md",
            "issues": ["ok"],
        }

    with patch.object(tools, "generate_vasp_report_context", fake_generate_context):
        result = tools.analyze_vasp_local_result("/tmp/vasp-output")

    assert result["ok"] is True
    assert result["risk"] == "write_local"
    assert result["local_job_dir"] == "/tmp/vasp-output"
    assert result["report_context_path"].endswith("report_context.md")


def test_analyze_vasp_local_result_structured_wraps_context():
    def fake_generate_context(local_job_dir: str):
        local_job_dir = str(local_job_dir)
        return {
            "success": True,
            "local_job_dir": local_job_dir,
            "analysis_dir": f"{local_job_dir}/analysis",
            "report_context_path": f"{local_job_dir}/analysis/report_context.md",
        }

    with patch.object(tools, "generate_vasp_report_context", fake_generate_context):
        result = tools.analyze_vasp_local_result_structured("/tmp/vasp-output")

    assert result["ok"] is True
    assert result["structured_arguments"]["local_job_dir"] == "/tmp/vasp-output"
    assert result["data"]["structured_arguments"]["local_job_dir"] == "/tmp/vasp-output"


def test_analyze_vasp_local_result_lists_collection_candidates():
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for name in ["job-a", "job-b"]:
            raw_output = root / name / "raw_output"
            raw_output.mkdir(parents=True)
            (raw_output / "OUTCAR").write_text("short\n", encoding="utf-8")

        result = tools.analyze_vasp_local_result(str(root))

        assert result["ok"] is False
        assert result["candidate_count"] == 2
        assert str(root / "job-a") in result["candidate_job_dirs"]
        assert str(root / "job-b") in result["candidate_job_dirs"]


def test_submit_prepared_job_requires_write_enable():
    with patch.dict(os.environ, {"HPC_AGENT_MCP_ENABLE_WRITE": ""}):
        result = tools.submit_prepared_job("#!/bin/bash\nhostname", confirm=True)

    assert result["ok"] is False
    assert result["risk"] == "write_execute"
    assert result["required_env"] == "HPC_AGENT_MCP_ENABLE_WRITE"


def test_submit_prepared_job_requires_confirm():
    with patch.dict(os.environ, {"HPC_AGENT_MCP_ENABLE_WRITE": "1"}):
        result = tools.submit_prepared_job("#!/bin/bash\nhostname", confirm=False)

    assert result["ok"] is False
    assert result["requires_confirmation"] is True


def test_sync_vasp_output_requires_write_enable():
    with patch.dict(os.environ, {"HPC_AGENT_MCP_ENABLE_WRITE": ""}):
        result = tools.sync_vasp_output("12345", confirm=True)

    assert result["ok"] is False
    assert result["required_env"] == "HPC_AGENT_MCP_ENABLE_WRITE"


def test_sync_vasp_output_structured_requires_write_enable():
    with patch.dict(os.environ, {"HPC_AGENT_MCP_ENABLE_WRITE": ""}):
        result = tools.sync_vasp_output_structured("12345", confirm=True)

    assert result["ok"] is False
    assert result["required_env"] == "HPC_AGENT_MCP_ENABLE_WRITE"
    assert result["structured_arguments"] == {"job_id": "12345", "confirm": True}


def test_prepare_cleanup_structured_wraps_preview():
    def fake_prepare_cleanup(request: str, intent: str):
        assert "12345" in request
        assert intent == "cleanup_remote_job"
        return ToolResult(
            success=True,
            message="cleanup preview",
            data={"pending_cleanup": {"targets": [{"path": "/remote/job"}]}},
            tool_call=ToolCall(tool="prepare_cleanup_remote_job", arguments={"job_id": "12345"}),
        )

    with patch.object(tools, "handle_cleanup_prepare_request", fake_prepare_cleanup):
        result = tools.prepare_cleanup_structured(cleanup_type="job", job_id="12345")

    assert result["ok"] is True
    assert result["risk"] == "destructive_preview"
    assert result["structured_arguments"]["job_id"] == "12345"
    assert result["data"]["structured_arguments"]["cleanup_type"] == "job"


def test_execute_cleanup_requires_destructive_enable():
    with patch.dict(os.environ, {"HPC_AGENT_MCP_ENABLE_DESTRUCTIVE": ""}):
        result = tools.execute_cleanup([{"path": "/remote/job"}], confirm=True)

    assert result["ok"] is False
    assert result["risk"] == "destructive"
    assert result["required_env"] == "HPC_AGENT_MCP_ENABLE_DESTRUCTIVE"


def test_get_cluster_info_wraps_retrieval():
    with (
        patch.object(tools, "load_documents", return_value=(["doc"], ["doc.txt#chunk0"])),
        patch.object(
            tools,
            "retrieve",
            return_value=[{"source": "doc.txt#chunk0", "content": "partition info", "score": 1.0}],
        ),
    ):
        result = tools.get_cluster_info("partition", top_k=3)

    assert result["ok"] is True
    assert result["risk"] == "read_only"
    assert result["results"][0]["source"] == "doc.txt#chunk0"


def test_list_skills_wraps_registry():
    class FakeSkill:
        name = "fake"
        description = "fake skill"
        type = "tool"
        intents = ("fake_intent",)
        triggers = ("fake",)
        handler = "module.handler"
        runtime = {"adapter": "question_to_text"}
        risk = "read_only"
        source = "builtin"
        path = "/tmp/fake/SKILL.md"

    class FakeRegistry:
        def all(self):
            return [FakeSkill()]

        def skipped(self):
            return []

    with patch.object(tools, "load_skill_registry", return_value=FakeRegistry()):
        result = tools.list_skills()

    assert result["ok"] is True
    assert result["skill_count"] == 1
    assert result["skills"][0]["name"] == "fake"


def test_discovery_resources_describe_capabilities_and_schema():
    capabilities = json.loads(resources.capabilities_json())
    schema = json.loads(resources.tool_schema_json())
    security = json.loads(resources.security_policy_json())
    examples = json.loads(resources.examples_json())

    assert capabilities["primary_tool"] == "hpc_agent_chat"
    assert "hpc_generate_sbatch_structured" in capabilities["structured_tools"]
    assert "hpc_prepare_vasp_job_structured" in capabilities["structured_tools"]
    assert "vasp_generate_inputs_structured" in capabilities["structured_tools"]
    assert "vasp_analyze_local_result_structured" in capabilities["structured_tools"]
    assert "hpc_query_job_structured" in capabilities["structured_tools"]
    assert "response_envelope" in schema
    assert "hpc_generate_sbatch_structured" in schema["tools"]
    assert "hpc_prepare_cleanup_structured" in schema["tools"]
    assert security["write_execute"]["requires"] == ["confirm=true", "HPC_AGENT_MCP_ENABLE_WRITE=1"]
    assert examples["structured"][0]["tool"] == "hpc_generate_sbatch_structured"


def test_generic_prompts_are_available():
    assert "hpc_agent_chat" in prompts.natural_language_agent()
    assert "confirm=true" in prompts.submit_safe_workflow()
    assert "vasp_sync_output" in prompts.vasp_full_workflow()
    assert "/health" in prompts.debug_connection()


def test_audit_log_records_sanitized_payload(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    result = {
        "ok": False,
        "message": "blocked",
        "required_env": "HPC_AGENT_MCP_ENABLE_WRITE",
        "requires_confirmation": True,
    }

    with patch.dict(os.environ, {"HPC_AGENT_MCP_AUDIT_LOG": str(log_path)}):
        audit.record_tool_call(
            "hpc_submit_prepared_job",
            risk="write_execute",
            arguments={"api_key": "secret", "visible": "ok"},
            result=result,
        )

    content = log_path.read_text(encoding="utf-8")
    assert "hpc_submit_prepared_job" in content
    assert "secret" not in content
    assert '"api_key": "***"' in content


def test_prompt_templates_include_safe_workflow_steps():
    assert "hpc_generate_sbatch" in prompts.submit_slurm_job()
    assert "hpc_query_job" in prompts.diagnose_slurm_error()
    assert "hpc_prepare_vasp_job" in prompts.prepare_vasp_job()
    assert "vasp_analyze_local_result" in prompts.analyze_vasp_result()
    assert "hpc_prepare_cleanup" in prompts.cleanup_remote_job()


def test_resources_return_expected_shapes():
    with patch.object(resources, "check_hpc_environment", return_value={"success": True, "checks": []}):
        assert '"success": true' in resources.config_status_json()

    with patch.object(resources, "list_jobs", return_value={"123": {"type": "slurm", "updated_at": "2026-01-01"}}):
        assert '"job_id": "123"' in resources.recent_jobs_json()
