import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from modules.core.paths import ENV_PATH
from modules.core.tool_calling import ToolCall, ToolResult, ensure_allowed_tool


load_dotenv(ENV_PATH)

DEFAULT_TEST_FILE_NAME = "test.py"
MAX_SLEEP_SECONDS = 24 * 60 * 60
SUPPORTED_TEST_COMMANDS_TEXT = "sleep N 秒、hostname、srun -n N hostname"
ASCII_LEFT_BOUNDARY = r"(?<![A-Za-z0-9_])"
ASCII_RIGHT_BOUNDARY = r"(?![A-Za-z0-9_])"
TEST_TOOL_GENERATE = "generate_test_file"
TEST_TOOL_GENERATE_AND_SUBMIT = "generate_and_submit_test_job"
TEST_TOOL_CLARIFY = "clarify_test_job"
ALLOWED_TEST_TOOLS = {
    TEST_TOOL_GENERATE,
    TEST_TOOL_GENERATE_AND_SUBMIT,
    TEST_TOOL_CLARIFY,
}
ALLOWED_TEST_KINDS = {"sleep", "hostname", "mpi_hostname"}


def get_local_workdir() -> Path:
    return Path(os.getenv("HPC_LOCAL_WORKDIR", "~/hpc-local-jobs")).expanduser()


def _format_slurm_time(total_seconds: int) -> str:
    total_seconds = max(60, int(total_seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _normalize_test_action(text: str) -> str:
    normalized = text.lower().replace(" ", "")
    run_keywords = [
        "并运行", "并提交", "运行", "提交", "跑起来", "跑一下",
        "跑个", "跑一个", "跑到超算", "提交到超算",
        "run", "submit", "launch",
    ]

    if any(keyword in normalized for keyword in run_keywords):
        return "run"

    return "generate"


def _safe_test_file_name(file_name: str | None) -> str:
    if not file_name:
        return DEFAULT_TEST_FILE_NAME

    safe_name = Path(str(file_name)).name
    if safe_name in {"", ".", ".."} or safe_name != str(file_name):
        raise ValueError("文件名不安全，请只提供文件名，不要包含路径。")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in {".py", ".sh"}:
        raise ValueError("目前测试文件只支持 .py 或 .sh 后缀。")

    return safe_name


def _parse_sleep_seconds(text: str) -> int | None:
    normalized = re.sub(r"\s+", " ", text.strip().lower())

    minute_patterns = [
        rf"{ASCII_LEFT_BOUNDARY}sleep\s*(\d+)\s*(?:m|min|mins|minute|minutes|分钟){ASCII_RIGHT_BOUNDARY}",
        r"(?:休眠|睡眠|等待|延时|延迟|暂停)\s*(\d+)\s*(?:分钟|m|min|mins|minute|minutes)",
        r"(\d+)\s*(?:分钟|m|min|mins|minute|minutes)\s*(?:sleep|休眠|睡眠|等待|延时|延迟|暂停)",
    ]

    for pattern in minute_patterns:
        match = re.search(pattern, normalized)
        if match:
            seconds = int(match.group(1)) * 60
            if 1 <= seconds <= MAX_SLEEP_SECONDS:
                return seconds

    patterns = [
        rf"{ASCII_LEFT_BOUNDARY}sleep\s*(\d+)\s*(?:s|sec|secs|second|seconds|秒)?{ASCII_RIGHT_BOUNDARY}",
        r"(?:休眠|睡眠|等待|延时|延迟|暂停)\s*(\d+)\s*(?:秒|s|sec|secs|second|seconds)?",
        r"(\d+)\s*(?:秒|s|sec|secs|second|seconds)\s*(?:sleep|休眠|睡眠|等待|延时|延迟|暂停)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            seconds = int(match.group(1))
            if 1 <= seconds <= MAX_SLEEP_SECONDS:
                return seconds

    return None


def _parse_mpi_hostname_tasks(text: str) -> int | None:
    normalized = re.sub(r"\s+", " ", text.strip().lower())

    match = re.search(
        rf"{ASCII_LEFT_BOUNDARY}mpirun\s+-np\s+(\d+)\s+hostname{ASCII_RIGHT_BOUNDARY}",
        normalized,
    )
    if match:
        tasks = int(match.group(1))
        return tasks if 1 <= tasks <= 1024 else None

    match = re.search(
        rf"{ASCII_LEFT_BOUNDARY}srun\s+-n\s+(\d+)\s+hostname{ASCII_RIGHT_BOUNDARY}",
        normalized,
    )
    if match:
        tasks = int(match.group(1))
        return tasks if 1 <= tasks <= 1024 else None

    match = re.search(r"(\d+)\s*(?:个|个)?\s*(?:mpi)?\s*(?:进程|任务|核|process|processes|rank|ranks).{0,20}(?:hostname|主机名|节点名)", normalized)
    if match:
        tasks = int(match.group(1))
        return tasks if 1 <= tasks <= 1024 else None

    if "mpi" in normalized and ("hostname" in normalized or "主机名" in normalized or "节点名" in normalized):
        return 4

    return None


def get_test_command_spec(text: str) -> dict | None:
    sleep_seconds = _parse_sleep_seconds(text)
    if sleep_seconds is not None:
        return {
            "kind": "sleep",
            "seconds": sleep_seconds,
            "command": f"sleep {sleep_seconds}",
            "cpus": 1,
            "time": _format_slurm_time(sleep_seconds + 60),
            "job_name": f"hpc_test_sleep_{sleep_seconds}",
        }

    mpi_tasks = _parse_mpi_hostname_tasks(text)
    if mpi_tasks is not None:
        return {
            "kind": "mpi_hostname",
            "tasks": mpi_tasks,
            "command": f"srun -n {mpi_tasks} hostname",
            "cpus": mpi_tasks,
            "time": "00:01:00",
            "job_name": f"hpc_test_mpi_hostname_{mpi_tasks}",
        }

    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if (
        re.search(rf"{ASCII_LEFT_BOUNDARY}hostname{ASCII_RIGHT_BOUNDARY}", normalized)
        or "主机名" in normalized
        or "节点名" in normalized
        or "打印节点" in normalized
        or "查看节点" in normalized
    ):
        return {
            "kind": "hostname",
            "command": "hostname",
            "cpus": 1,
            "time": "00:01:00",
            "job_name": "hpc_test_hostname",
        }

    return None


def _spec_from_tool_arguments(arguments: dict) -> dict | None:
    kind = arguments.get("kind")

    if kind == "sleep":
        seconds = arguments.get("seconds")
        if seconds is None:
            return None

        seconds = int(seconds)
        if not 1 <= seconds <= MAX_SLEEP_SECONDS:
            raise ValueError(f"sleep 秒数必须在 1 到 {MAX_SLEEP_SECONDS} 之间。")

        return {
            "kind": "sleep",
            "seconds": seconds,
            "command": f"sleep {seconds}",
            "cpus": 1,
            "time": _format_slurm_time(seconds + 60),
            "job_name": f"hpc_test_sleep_{seconds}",
        }

    if kind == "hostname":
        return {
            "kind": "hostname",
            "command": "hostname",
            "cpus": 1,
            "time": "00:01:00",
            "job_name": "hpc_test_hostname",
        }

    if kind == "mpi_hostname":
        tasks = int(arguments.get("mpi_tasks") or arguments.get("tasks") or 4)
        if not 1 <= tasks <= 1024:
            raise ValueError("MPI 进程数必须在 1 到 1024 之间。")

        return {
            "kind": "mpi_hostname",
            "tasks": tasks,
            "command": f"srun -n {tasks} hostname",
            "cpus": tasks,
            "time": "00:01:00",
            "job_name": f"hpc_test_mpi_hostname_{tasks}",
        }

    return None


def detect_test_command(text: str) -> str | None:
    spec = get_test_command_spec(text)
    return spec["kind"] if spec else None


def _has_test_action(text: str) -> bool:
    normalized = text.lower().replace(" ", "")
    action_keywords = [
        "生成", "创建", "写一个", "写个", "帮我写",
        "来一个", "弄一个", "做一个",
        "generate", "create", "write", "make",
    ]

    return any(keyword in normalized for keyword in action_keywords)


def _has_test_target(text: str) -> bool:
    text_without_paths = re.sub(
        r"(?:~|/|\./|\../)?[A-Za-z0-9_./-]+\.(?:py|sh|slurm|sbatch)",
        "",
        text.lower(),
    )
    normalized = text_without_paths.replace(" ", "")
    target_keywords = [
        "测试", "smoketest", "smoke测试",
        "测试文件", "测试脚本", "测试作业", "测试任务",
        "testjob", "testscript",
    ]

    return (
        any(keyword in normalized for keyword in target_keywords)
        or re.search(rf"{ASCII_LEFT_BOUNDARY}test{ASCII_RIGHT_BOUNDARY}", text_without_paths) is not None
    )


def is_test_file_request(text: str) -> bool:
    return is_potential_test_job_request(text) and (
        detect_test_command(text) is not None
        or _has_test_target(text)
    )


def is_potential_test_job_request(text: str) -> bool:
    return (
        (_has_test_action(text) or _normalize_test_action(text) == "run")
        and (_has_test_target(text) or detect_test_command(text) is not None)
    )


def is_test_run_request(text: str) -> bool:
    return is_test_file_request(text) and _normalize_test_action(text) == "run"


def extract_test_file_name(text: str) -> str:
    patterns = [
        r"(?:文件名|保存为|命名为|叫做|名为)\s*[:：=]?\s*([A-Za-z0-9_.-]+\.(?:py|sh))",
        r"\b(?:file|filename|save as|named)\s*[:：=]?\s*([A-Za-z0-9_.-]+\.(?:py|sh))",
        r"\b([A-Za-z0-9_.-]+\.(?:py|sh))\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return Path(match.group(1)).name

    return DEFAULT_TEST_FILE_NAME


def make_rule_based_test_tool_call(text: str) -> ToolCall | None:
    spec = get_test_command_spec(text)
    if not spec:
        return None

    return ToolCall(
        tool=(
            TEST_TOOL_GENERATE_AND_SUBMIT
            if _normalize_test_action(text) == "run"
            else TEST_TOOL_GENERATE
        ),
        arguments={
            "kind": spec["kind"],
            "seconds": spec.get("seconds"),
            "mpi_tasks": spec.get("tasks"),
            "file_name": extract_test_file_name(text),
        },
        source="rules",
        confidence=1.0,
    )


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_test_tool_call_with_llm(user_request: str) -> dict | None:
    from modules.knowledge.knowledge_base import client

    messages = [
        {
            "role": "system",
            "content": """
你是 HPC Agent 的测试作业工具参数解析器。
只能把用户请求解析成严格 JSON，不要输出 Markdown，不要解释。

允许的 tool:
- generate_test_file
- generate_and_submit_test_job
- clarify_test_job

允许的 kind:
- sleep
- hostname
- mpi_hostname

JSON 格式:
{
  "tool": "generate_test_file | generate_and_submit_test_job | clarify_test_job",
  "arguments": {
    "kind": "sleep | hostname | mpi_hostname | null",
    "seconds": 90,
    "mpi_tasks": 4,
    "file_name": "test.py",
    "question": "需要向用户追问的问题"
  }
}

规则:
1. 用户要求运行、提交、跑一下、跑起来时，tool 用 generate_and_submit_test_job。
2. 用户只要求生成/创建/写文件时，tool 用 generate_test_file。
3. sleep 必须有明确秒数；“一分半钟”解析为 90 秒，“两分钟”解析为 120 秒。
4. hostname 不需要 seconds。
5. mpi hostname 默认 mpi_tasks=4，除非用户明确指定其他进程数。
6. 如果测试类型或必要参数不明确，tool 用 clarify_test_job，并在 question 里提出一个简短中文问题。
7. 不要解析任意 shell 命令，只能使用上面的安全测试类型。
""",
        },
        {
            "role": "user",
            "content": user_request,
        },
    ]

    response = client.chat.completions.create(
        model=os.getenv("PARATERA_MODEL", "DeepSeek-V4-Pro"),
        messages=messages,
        max_tokens=300,
        stream=False,
        timeout=30,
    )
    return _extract_json_object(response.choices[0].message.content or "")


def validate_test_tool_call(tool_call: dict | ToolCall | None) -> ToolCall:
    if not tool_call:
        return ToolCall(
            tool=TEST_TOOL_CLARIFY,
            arguments={
                "question": (
                    "你想生成哪类测试作业？目前支持 sleep N 秒、hostname、"
                    "srun -n N hostname。"
                ),
            },
            source="validator",
        )

    call = ensure_allowed_tool(tool_call, ALLOWED_TEST_TOOLS)

    arguments = dict(call.arguments)
    if call.tool == TEST_TOOL_CLARIFY:
        question = arguments.get("question") or (
            "请补充测试作业类型和必要参数，例如 sleep 60 秒或 hostname。"
        )
        return ToolCall(
            tool=TEST_TOOL_CLARIFY,
            arguments={"question": question},
            source=call.source,
            confidence=call.confidence,
            metadata=call.metadata,
        )

    kind = arguments.get("kind")
    if kind not in ALLOWED_TEST_KINDS:
        return ToolCall(
            tool=TEST_TOOL_CLARIFY,
            arguments={
                "question": (
                    "你想生成哪类测试作业？目前支持 sleep、hostname、"
                    "mpi hostname。"
                ),
            },
            source=call.source or "validator",
            metadata={"original_tool": call.tool},
        )

    if kind == "sleep" and arguments.get("seconds") is None:
        return ToolCall(
            tool=TEST_TOOL_CLARIFY,
            arguments={"question": "你想 sleep 多久？例如 60 秒、90 秒或 2 分钟。"},
            source=call.source or "validator",
            metadata={"original_tool": call.tool},
        )

    arguments["file_name"] = _safe_test_file_name(arguments.get("file_name"))
    spec = _spec_from_tool_arguments(arguments)
    if not spec:
        return ToolCall(
            tool=TEST_TOOL_CLARIFY,
            arguments={"question": "请补充测试作业类型和必要参数。"},
            source=call.source or "validator",
            metadata={"original_tool": call.tool},
        )

    arguments["spec"] = spec
    return ToolCall(
        tool=call.tool,
        arguments=arguments,
        source=call.source,
        confidence=call.confidence,
        needs_confirmation=call.needs_confirmation,
        metadata=call.metadata,
    )


def parse_test_job_tool_call_object(user_request: str, llm_parser=None) -> ToolCall:
    rule_call = make_rule_based_test_tool_call(user_request)
    if rule_call:
        return validate_test_tool_call(rule_call)

    if not is_potential_test_job_request(user_request):
        return validate_test_tool_call(None)

    parser = llm_parser or parse_test_tool_call_with_llm
    try:
        llm_call = parser(user_request)
    except Exception:
        llm_call = None

    if llm_call:
        llm_call["source"] = llm_call.get("source", "llm")

    return validate_test_tool_call(llm_call)


def parse_test_job_tool_call(user_request: str, llm_parser=None) -> dict:
    return parse_test_job_tool_call_object(user_request, llm_parser=llm_parser).to_dict()


def test_file_run_command(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()

    if suffix == ".py":
        return f"python3 {file_name}"

    if suffix == ".sh":
        return f"bash {file_name}"

    raise ValueError("目前测试文件只支持 .py 或 .sh 后缀。")


def build_python_test_file(command_key: str) -> str:
    spec = get_test_command_spec(command_key)
    if spec and spec["kind"] == "sleep":
        return """#!/usr/bin/env python3
import time

time.sleep({seconds})
""".format(seconds=spec["seconds"])

    if spec and spec["kind"] == "hostname":
        return """#!/usr/bin/env python3
import socket

print(socket.gethostname())
"""

    if spec and spec["kind"] == "mpi_hostname":
        return """#!/usr/bin/env python3
import subprocess

subprocess.check_call(["srun", "-n", "{tasks}", "hostname"])
""".format(tasks=spec["tasks"])

    raise ValueError("不支持的测试命令。")


def build_shell_test_file(command_key: str) -> str:
    spec = get_test_command_spec(command_key)

    if not spec:
        raise ValueError("不支持的测试命令。")

    return f"""#!/bin/bash
set -euo pipefail

{spec["command"]}
"""


def build_test_file_content(command_key: str, file_name: str) -> str:
    suffix = Path(file_name).suffix.lower()

    if suffix == ".sh":
        return build_shell_test_file(command_key)

    if suffix == ".py":
        return build_python_test_file(command_key)

    raise ValueError("目前测试文件只支持 .py 或 .sh 后缀。")


def generate_hpc_test_file_result(user_request: str, tool_call: dict | ToolCall | None = None) -> dict:
    tool_call = (
        ToolCall.from_mapping(tool_call)
        if tool_call
        else parse_test_job_tool_call_object(user_request)
    )

    if tool_call.tool == TEST_TOOL_CLARIFY:
        return {
            "success": False,
            "spec": None,
            "file_path": None,
            "message": tool_call.arguments["question"],
            "tool_call": tool_call.to_dict(),
        }

    spec = tool_call.arguments["spec"]

    if not spec:
        return {
            "success": False,
            "spec": None,
            "file_path": None,
            "message": (
                f"目前只支持生成这些安全测试文件：{SUPPORTED_TEST_COMMANDS_TEXT}。"
            ),
        }

    file_name = tool_call.arguments["file_name"]

    try:
        content = build_test_file_content(spec["command"], file_name)
    except ValueError as error:
        return {
            "success": False,
            "spec": spec,
            "file_path": None,
            "message": str(error),
        }

    workdir = get_local_workdir()
    workdir.mkdir(parents=True, exist_ok=True)

    file_path = workdir / file_name
    file_path.write_text(content, encoding="utf-8")

    if file_path.suffix.lower() == ".sh":
        file_path.chmod(file_path.stat().st_mode | 0o111)

    return {
        "success": True,
        "spec": spec,
        "command_key": spec["kind"],
        "command": spec["command"],
        "file_path": file_path,
        "file_name": file_name,
        "content": content,
        "run_command": test_file_run_command(file_name),
        "tool_call": tool_call.to_dict(),
        "message": (
            "已生成超算测试文件。\n\n"
            f"测试命令: {spec['command']}\n"
            f"文件路径: {file_path}\n\n"
            "后续可以让 Agent 提交这个文件，例如：帮我提交 "
            f"{file_path}，1 核，1 分钟"
        ),
    }


def generate_hpc_test_file(user_request: str, tool_call: dict | ToolCall | None = None) -> str:
    return generate_hpc_test_file_result(user_request, tool_call=tool_call)["message"]


def build_test_submit_request(generated: dict) -> str:
    resources = generated["spec"]
    return (
        "帮我提交一个作业"
        f"运行 {generated['run_command']}，"
        f"{resources['cpus']} 核，"
        f"运行时间 {resources['time']}，"
        f"作业名 {resources['job_name']}"
    )


def submit_hpc_test_file(user_request: str, submit_func=None, tool_call: dict | ToolCall | None = None) -> str:
    generated = generate_hpc_test_file_result(user_request, tool_call=tool_call)

    if not generated["success"]:
        return generated["message"]

    from modules.slurm.job_submitter import prepare_submit_script, submit_prepared_script

    prepared = prepare_submit_script(build_test_submit_request(generated))

    if not prepared["ready"]:
        return (
            f"{generated['message']}\n\n"
            "测试文件已生成，但提交脚本准备失败：\n"
            f"{prepared['message']}"
        )

    uploaded_files = [
        {
            "name": generated["file_name"],
            "content": Path(generated["file_path"]).read_bytes(),
        }
    ]
    submit = submit_func or submit_prepared_script
    result = submit(prepared["script"], uploaded_files=uploaded_files)

    if result.get("success"):
        if result.get("job_id"):
            from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE

            GLOBAL_CONVERSATION_STATE.record_job(
                result.get("job_id"),
                result.get("raw", {}).get("remote_workdir"),
                {
                    "kind": "test",
                    "source": "test_run",
                    "command": generated.get("command"),
                },
            )

        return (
            f"{generated['message']}\n\n"
            "已按普通 Slurm 作业流程上传并提交。\n\n"
            f"{result['answer']}"
        )

    return (
        f"{generated['message']}\n\n"
        "测试文件已生成，但自动提交失败。\n\n"
        f"{result.get('answer', result)}"
    )


def execute_test_job_tool_call(tool_call: dict | ToolCall, user_request: str = "", submit_func=None) -> ToolResult:
    call = ToolCall.from_mapping(tool_call)

    if call.tool == TEST_TOOL_CLARIFY:
        return ToolResult(
            success=False,
            message=call.arguments["question"],
            tool_call=call,
            data={"needs_clarification": True},
        )

    if call.tool == TEST_TOOL_GENERATE_AND_SUBMIT:
        message = submit_hpc_test_file(user_request, submit_func=submit_func, tool_call=call)
        return ToolResult(
            success="已按普通 Slurm 作业流程上传并提交" in message,
            message=message,
            tool_call=call,
        )

    if call.tool == TEST_TOOL_GENERATE:
        result = generate_hpc_test_file_result(user_request, tool_call=call)
        return ToolResult(
            success=bool(result.get("success")),
            message=result["message"],
            data=result,
            tool_call=call,
        )

    return ToolResult(
        success=False,
        message=f"不支持的测试作业工具: {call.tool}",
        tool_call=call,
    )


def handle_hpc_test_request(user_request: str) -> str:
    tool_call = parse_test_job_tool_call_object(user_request)
    return execute_test_job_tool_call(tool_call, user_request=user_request).message
