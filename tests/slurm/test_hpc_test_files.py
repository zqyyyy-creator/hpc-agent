import os
import tempfile
from pathlib import Path

from tests import _bootstrap  # noqa: F401

from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE
from modules.slurm.hpc_test_files import (
    execute_test_job_tool_call,
    generate_hpc_test_file,
    get_test_command_spec,
    parse_test_job_tool_call_object,
    parse_test_job_tool_call,
    is_test_run_request,
    submit_hpc_test_file,
)
from modules.core.tool_calling import ToolCall
from modules.routing.router import detect_intent


def with_temp_workdir(callback):
    original = os.environ.get("HPC_LOCAL_WORKDIR")

    with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
        os.environ["HPC_LOCAL_WORKDIR"] = tmpdir
        try:
            callback(Path(tmpdir))
        finally:
            if original is None:
                os.environ.pop("HPC_LOCAL_WORKDIR", None)
            else:
                os.environ["HPC_LOCAL_WORKDIR"] = original


def test_sleep_test_file_defaults_to_test_py():
    def check(workdir: Path):
        request = "生成一个 sleep 60 的测试作业脚本"
        answer = generate_hpc_test_file(request)
        path = workdir / "test.py"

        assert detect_intent(request) == "generate_test_file"
        assert path.is_file()
        assert "time.sleep(60)" in path.read_text(encoding="utf-8")
        assert str(path) in answer

    with_temp_workdir(check)


def test_variable_sleep_seconds_are_supported():
    def check(workdir: Path):
        cases = {
            "生成一个 sleep 90 的测试作业脚本": 90,
            "生成一个sleep 60的测试作业": 60,
            "生成一个sleep90测试作业": 90,
            "帮我创建等待120秒的测试文件": 120,
            "写个休眠 2 分钟的 smoke test": 120,
            "generate a sleep 3 minutes test script": 180,
        }

        for request, seconds in cases.items():
            answer = generate_hpc_test_file(request)
            path = workdir / "test.py"
            content = path.read_text(encoding="utf-8")

            assert detect_intent(request) == "generate_test_file"
            assert f"time.sleep({seconds})" in content
            assert f"sleep {seconds}" in answer

    with_temp_workdir(check)


def test_hostname_shell_test_file_uses_requested_name():
    def check(workdir: Path):
        request = "帮我生成 hostname 测试文件，文件名 node_check.sh"
        answer = generate_hpc_test_file(request)
        path = workdir / "node_check.sh"

        assert detect_intent(request) == "generate_test_file"
        assert path.is_file()
        assert "hostname" in path.read_text(encoding="utf-8")
        assert os.access(path, os.X_OK)
        assert str(path) in answer

    with_temp_workdir(check)


def test_hostname_natural_language_variants():
    requests = [
        "生成一个打印节点名的测试脚本",
        "创建查看主机名的测试文件",
        "生成hostname测试作业",
        "generate a node hostname smoke test",
    ]

    for request in requests:
        spec = get_test_command_spec(request)
        assert detect_intent(request) == "generate_test_file"
        assert spec["kind"] == "hostname"
        assert spec["command"] == "hostname"


def test_mpi_hostname_test_file():
    def check(workdir: Path):
        request = "创建 mpirun -np 4 hostname 测试脚本"
        answer = generate_hpc_test_file(request)
        path = workdir / "test.py"
        content = path.read_text(encoding="utf-8")

        assert detect_intent(request) == "generate_test_file"
        assert '["mpirun", "-np", "4", "hostname"]' in content
        assert "mpirun -np 4 hostname" in answer

    with_temp_workdir(check)


def test_mpi_hostname_natural_language_with_task_count():
    def check(workdir: Path):
        request = "生成一个 8 个 MPI 进程打印节点名的测试脚本"
        answer = generate_hpc_test_file(request)
        path = workdir / "test.py"
        content = path.read_text(encoding="utf-8")

        assert detect_intent(request) == "generate_test_file"
        assert '["mpirun", "-np", "8", "hostname"]' in content
        assert "mpirun -np 8 hostname" in answer

    with_temp_workdir(check)


def test_sleep_test_file_and_run_uses_normal_submit_flow():
    def check(workdir: Path):
        captured = {}
        original_last_job_id = GLOBAL_CONVERSATION_STATE.last_job_id

        def fake_submit(script, uploaded_files=None):
            captured["script"] = script
            captured["uploaded_files"] = uploaded_files or []
            return {
                "success": True,
                "job_id": "12345",
                "answer": (
                    "作业已提交成功。\n\n"
                    "Job ID: 12345\n"
                    "远程作业目录: /remote/hpc_test_sleep_60_20260616_000000_000001\n"
                    "远程脚本: /remote/hpc_test_sleep_60_20260616_000000_000001/job.sh"
                ),
            }

        request = "生成一个sleep 60的测试作业并运行"
        answer = submit_hpc_test_file(request, submit_func=fake_submit)
        path = workdir / "test.py"

        assert is_test_run_request(request)
        assert detect_intent(request) == "generate_test_file"
        assert path.is_file()
        assert "python test.py" in captured["script"]
        assert "#SBATCH --job-name=hpc_test_sleep_60" in captured["script"]
        assert "#SBATCH --cpus-per-task=1" in captured["script"]
        assert "#SBATCH --time=00:02:00" in captured["script"]
        assert captured["uploaded_files"][0]["name"] == "test.py"
        assert b"time.sleep(60)" in captured["uploaded_files"][0]["content"]
        assert "Job ID: 12345" in answer
        assert "已按普通 Slurm 作业流程上传并提交" in answer
        assert GLOBAL_CONVERSATION_STATE.last_job_id == "12345"
        GLOBAL_CONVERSATION_STATE.last_job_id = original_last_job_id

    with_temp_workdir(check)


def test_mpi_test_file_and_run_requests_four_cpus():
    def check(_workdir: Path):
        captured = {}

        def fake_submit(script, uploaded_files=None):
            captured["script"] = script
            captured["uploaded_files"] = uploaded_files or []
            return {"success": True, "job_id": "12346", "answer": "Job ID: 12346"}

        request = "创建mpirun -np 4 hostname测试脚本并运行"
        answer = submit_hpc_test_file(request, submit_func=fake_submit)

        assert "#SBATCH --job-name=hpc_test_mpi_hostname" in captured["script"]
        assert "#SBATCH --cpus-per-task=4" in captured["script"]
        assert "python test.py" in captured["script"]
        assert b"mpirun" in captured["uploaded_files"][0]["content"]
        assert "Job ID: 12346" in answer

    with_temp_workdir(check)


def test_variable_sleep_run_uses_dynamic_job_time():
    def check(_workdir: Path):
        captured = {}

        def fake_submit(script, uploaded_files=None):
            captured["script"] = script
            captured["uploaded_files"] = uploaded_files or []
            return {"success": True, "job_id": "12347", "answer": "Job ID: 12347"}

        request = "生成一个 sleep 120 的测试作业脚本并运行"
        answer = submit_hpc_test_file(request, submit_func=fake_submit)

        assert "#SBATCH --job-name=hpc_test_sleep_120" in captured["script"]
        assert "#SBATCH --time=00:03:00" in captured["script"]
        assert b"time.sleep(120)" in captured["uploaded_files"][0]["content"]
        assert "Job ID: 12347" in answer

    with_temp_workdir(check)


def test_rule_based_tool_call_for_test_job():
    tool_call = parse_test_job_tool_call("生成一个sleep90测试作业并运行")

    assert tool_call["tool"] == "generate_and_submit_test_job"
    assert tool_call["source"] == "rules"
    assert tool_call["arguments"]["kind"] == "sleep"
    assert tool_call["arguments"]["seconds"] == 90
    assert tool_call["arguments"]["file_name"] == "test.py"
    assert tool_call["arguments"]["spec"]["command"] == "sleep 90"
    assert tool_call["arguments"]["spec"]["time"] == "00:02:30"

    tool_call_object = parse_test_job_tool_call_object("生成一个sleep90测试作业并运行")
    assert isinstance(tool_call_object, ToolCall)
    assert tool_call_object.tool == "generate_and_submit_test_job"
    assert tool_call_object.arguments["spec"]["command"] == "sleep 90"


def test_llm_tool_call_fallback_for_fuzzy_sleep_request():
    def fake_parser(_request: str):
        return {
            "tool": "generate_and_submit_test_job",
            "arguments": {
                "kind": "sleep",
                "seconds": 90,
                "file_name": "wait.py",
            },
        }

    tool_call = parse_test_job_tool_call(
        "帮我弄个等一分半钟的测试任务，跑一下",
        llm_parser=fake_parser,
    )

    assert tool_call["tool"] == "generate_and_submit_test_job"
    assert tool_call["source"] == "llm"
    assert tool_call["arguments"]["file_name"] == "wait.py"
    assert tool_call["arguments"]["spec"]["command"] == "sleep 90"


def test_ambiguous_test_job_asks_for_clarification():
    tool_call = parse_test_job_tool_call("跑个测试任务", llm_parser=lambda _request: None)

    assert tool_call["tool"] == "clarify_test_job"
    assert "支持" in tool_call["arguments"]["question"] or "补充" in tool_call["arguments"]["question"]


def test_llm_tool_call_rejects_unsafe_file_name():
    def fake_parser(_request: str):
        return {
            "tool": "generate_test_file",
            "arguments": {
                "kind": "hostname",
                "file_name": "../bad.py",
            },
        }

    try:
        parse_test_job_tool_call("生成一个测试文件", llm_parser=fake_parser)
    except ValueError as error:
        assert "文件名不安全" in str(error)
    else:
        raise AssertionError("Expected unsafe file name to be rejected")


def test_execute_test_job_tool_call_returns_tool_result():
    def check(workdir: Path):
        tool_call = parse_test_job_tool_call_object("生成hostname测试作业")
        result = execute_test_job_tool_call(tool_call, user_request="生成hostname测试作业")
        path = workdir / "test.py"

        assert result.success
        assert result.tool_call.tool == "generate_test_file"
        assert path.is_file()
        assert "hostname" in result.message
        assert result.data["file_name"] == "test.py"

    with_temp_workdir(check)


if __name__ == "__main__":
    test_sleep_test_file_defaults_to_test_py()
    test_variable_sleep_seconds_are_supported()
    test_hostname_shell_test_file_uses_requested_name()
    test_hostname_natural_language_variants()
    test_mpi_hostname_test_file()
    test_mpi_hostname_natural_language_with_task_count()
    test_sleep_test_file_and_run_uses_normal_submit_flow()
    test_mpi_test_file_and_run_requests_four_cpus()
    test_variable_sleep_run_uses_dynamic_job_time()
    test_rule_based_tool_call_for_test_job()
    test_llm_tool_call_fallback_for_fuzzy_sleep_request()
    test_ambiguous_test_job_asks_for_clarification()
    test_llm_tool_call_rejects_unsafe_file_name()
    test_execute_test_job_tool_call_returns_tool_result()
    print("All HPC test file checks passed.")
