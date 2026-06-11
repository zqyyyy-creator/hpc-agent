import logging
import re
import shutil
import subprocess
import base64
from pathlib import Path

import jieba


jieba.setLogLevel(logging.ERROR)


def _extract_local_file_candidates(text: str):
    candidates = re.findall(
        r"(?:~|/|\./|\../)?[A-Za-z0-9_./-]+\.(?:py|sh|slurm|sbatch)",
        text,
    )
    cleaned_candidates = []

    for candidate in candidates:
        cleaned = candidate.strip("`'\"，,。；;:：")

        if cleaned not in cleaned_candidates:
            cleaned_candidates.append(cleaned)

    return cleaned_candidates


def _extract_local_file_paths(text: str):
    paths = []

    for candidate in _extract_local_file_candidates(text):
        path = Path(candidate).expanduser()

        if path.is_file():
            paths.append(path)

    return paths


def _has_explicit_run_command(text: str):
    return bool(
        re.search(r"\bpython(?:3)?\s+\S+\.py\b", text)
        or re.search(r"\bbash\s+\S+\.sh\b", text)
        or re.search(r"\./[A-Za-z0-9_./-]+", text)
    )


def _uploaded_files_from_paths(paths):
    return [
        {
            "name": path.name,
            "content": path.read_bytes(),
        }
        for path in paths
    ]


def _infer_run_command(uploaded_files):
    for item in uploaded_files:
        name = item["name"]

        if name.endswith(".py"):
            return f"python {name}"

    for item in uploaded_files:
        name = item["name"]

        if name.endswith(".sh"):
            return f"bash {name}"

    return None


def _copy_to_clipboard(text: str):
    errors = []

    try:
        import pyperclip

        pyperclip.copy(text)
        return True, ""
    except Exception as error:
        errors.append(f"pyperclip: {type(error).__name__}: {error}")

    powershell = shutil.which("powershell.exe")

    if powershell:
        try:
            encoded_text = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
            command = [
                powershell,
                "-NoProfile",
                "-Command",
                (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    f"[Windows.Forms.Clipboard]::SetText([Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_text}')))"
                ),
            ]
            subprocess.run(command, check=True, timeout=5)
            return True, ""
        except Exception as error:
            errors.append(f"powershell.exe: {type(error).__name__}: {error}")

    commands = [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
        ["pbcopy"],
        ["clip"],
        ["clip.exe"],
    ]

    for command in commands:
        if not shutil.which(command[0]):
            continue

        try:
            subprocess.run(
                command,
                input=text,
                text=True,
                check=True,
                timeout=3,
            )
            return True, ""
        except Exception as error:
            errors.append(f"{command[0]}: {type(error).__name__}: {error}")

    return False, "; ".join(errors) or "没有找到 wl-copy/xclip/xsel/pbcopy/clip.exe 等剪贴板命令"


def _compact_remote_dir(remote_workdir: str):
    if not remote_workdir or remote_workdir == "-":
        return "-"

    return Path(remote_workdir).name or remote_workdir


def _last_nonempty_lines(text: str, limit: int = 5):
    lines = [line for line in text.splitlines() if line.strip()]

    if not lines:
        return ""

    return "\n".join(lines[-limit:])


def run_textual_cli():
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Header, Input, RichLog, Static
    except ModuleNotFoundError:
        print(
            "Textual 依赖尚未安装。\n\n"
            "请先运行:\n"
            "  uv sync\n\n"
            "或手动安装:\n"
            "  .venv/bin/python -m pip install textual\n"
        )
        return

    from modules.error_diagnoser import ErrorDiagnoser
    from modules.job_query import (
        execute_cleanup_remote_jobs,
        extract_job_id,
        prepare_cleanup_all_remote_jobs,
        prepare_cleanup_remote_job,
        query_job_error,
        query_job_output,
        query_job_status,
        query_remote_agent_jobs,
    )
    from modules.job_submitter import (
        prepare_submit_script,
        prepare_vasp_submit_script,
        register_existing_vasp_job_from_text,
        submit_prepared_script,
        submit_prepared_vasp_script,
    )
    from modules.knowledge_base import ask_llm, load_documents, retrieve
    from modules.router import detect_intent
    from modules.slurm_assistant import (
        build_resource_recommendation_text,
        extract_command,
        generate_sbatch_script,
        suggest_slurm_parameters,
    )
    from modules.slurm_tools import (
        HOST,
        REMOTE_WORKDIR,
        USERNAME,
        get_job_monitor_snapshot,
        validate_monitorable_job,
    )
    from modules.vasp_assistant import generate_vasp_sbatch_script

    class HPCAgentTUI(App):
        CSS = """
        Screen {
            layout: vertical;
            background: #101316;
            color: #f1f5f2;
        }

        Header {
            background: #181d21;
            color: #f6f7f2;
        }

        #top-bar {
            height: 3;
            padding: 0 1;
            background: #1c2227;
            color: #f6f7f2;
            border-bottom: solid #22c7a9;
        }

        #body {
            layout: horizontal;
            height: 1fr;
            background: #101316;
        }

        #chat-pane {
            width: 1fr;
            min-width: 42;
            background: #14181b;
        }

        #right-pane {
            width: 38;
            min-width: 30;
            background: #111619;
            border-left: solid #22c7a9;
        }

        #input-bar {
            height: 4;
            background: #101316;
            border-top: solid #22c7a9;
        }

        .pane-title {
            height: 1;
            padding: 0 1;
            background: #20272b;
            color: #9fffe8;
            text-style: bold;
        }

        RichLog {
            height: 1fr;
            padding: 0 1;
            background: #14181b;
            color: #f1f5f2;
        }

        #chat-log {
            overflow-x: hidden;
        }

        #monitor {
            height: 1fr;
            padding: 1;
            background: #111619;
            color: #f1f5f2;
        }

        Input {
            height: 3;
            background: #1b2024;
            color: #f6f7f2;
            border: solid #3cd6b5;
        }

        Input:focus {
            border: solid #f5b84b;
        }
        """

        BINDINGS = [
            ("ctrl+r", "refresh_status", "刷新状态"),
            ("ctrl+y", "copy_last_reply", "复制回复"),
            ("ctrl+s", "submit_pending", "提交作业"),
            ("escape", "cancel_pending", "返回/取消"),
            ("tab", "next_monitor", "切换监控"),
            ("ctrl+x", "quit", "退出"),
            ("f10", "quit", "退出"),
            ("q", "quit", "退出"),
        ]

        def __init__(self):
            super().__init__()
            self.documents = []
            self.sources = []
            self.diagnoser = ErrorDiagnoser()
            self.pending_submission = None
            self.pending_cleanup = None
            self.current_job_id = None
            self.monitored_job_ids = []
            self.monitor_snapshots = {}
            self.monitor_active = {}
            self.active_monitor_index = 0
            self.monitor_refresh_running = False
            self.failure_notices_shown = set()
            self.history = []
            self.last_assistant_reply = None

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(self._top_text(), id="top-bar")
            with Horizontal(id="body"):
                with Vertical(id="chat-pane"):
                    yield Static("Chat", classes="pane-title")
                    yield RichLog(id="chat-log", wrap=True, highlight=True, markup=True, min_width=1)
                with Vertical(id="right-pane"):
                    yield Static("Job Monitor", classes="pane-title")
                    yield Static("输入“监控 JOBID”开始监控。", id="monitor")
            with Vertical(id="input-bar"):
                yield Input(placeholder="Command HPC Agent...  Ctrl+R 刷新状态 / Ctrl+Y 复制回复 / Ctrl+S 提交", id="command-input")

        def on_mount(self):
            self.documents, self.sources = load_documents()
            self._write_assistant(
                "HPC Agent TUI 已启动。\n\n"
                "中间是对话；右侧是显式 Job 监控区；底部输入命令。\n"
                "输入“监控 JOBID”后，右侧会显示 squeue 状态、远端目录和 stdout/stderr 最近 50 行。"
            )
            self.set_interval(15, self._schedule_monitor_refresh)
            self.query_one("#command-input", Input).focus()

        def _top_text(self):
            return (
                f"HPC: {HOST or '-'}    User: {USERNAME or '-'}    "
                f"Remote: {REMOTE_WORKDIR or '-'}    Keys: Ctrl+R 刷新 / Ctrl+Y 复制 / Ctrl+S 提交 / Tab 切换"
            )

        def _write_user(self, text: str):
            self.query_one("#chat-log", RichLog).write(f"[bold #67e8c9]你:[/bold #67e8c9] {text}")

        def _write_assistant(self, text: str):
            self.last_assistant_reply = text
            self.query_one("#chat-log", RichLog).write(f"[bold #b8f26a]HPC Agent:[/bold #b8f26a]\n{text}")

        def _write_system(self, text: str):
            self.query_one("#chat-log", RichLog).write(f"[bold #f5b84b]{text}[/bold #f5b84b]")

        def on_key(self, event):
            if event.key == "tab":
                event.prevent_default()
                event.stop()
                self.action_next_monitor()

        def _is_monitor_request(self, text: str):
            normalized = text.lower().replace(" ", "")
            return (
                ("监控" in normalized or "monitor" in normalized)
                and "取消监控" not in normalized
                and "cancelmonitor" not in normalized
                and extract_job_id(text)
            )

        def _is_cancel_monitor_request(self, text: str):
            normalized = text.lower().replace(" ", "")
            return (
                ("取消监控" in normalized or "cancelmonitor" in normalized)
                and extract_job_id(text)
            )

        def _select_latest_job_from_answer(self, answer: str):
            matches = re.findall(r"Job ID:\s*(\d+)", answer)

            if matches and not self.monitored_job_ids:
                self.current_job_id = matches[-1]

        def on_input_submitted(self, event: Input.Submitted):
            question = event.value.strip()
            event.input.value = ""

            if not question:
                return

            self.history.append(question)
            self._write_user(question)

            if self.pending_submission and question in {"确认", "确认提交", "yes", "y", "submit"}:
                self._submit_pending()
                return

            if self.pending_submission and question in {"取消", "取消提交", "no", "n", "cancel"}:
                self.pending_submission = None
                self._write_system("已取消提交。")
                return

            if self.pending_cleanup and question == "确认清理":
                answer = execute_cleanup_remote_jobs(self.pending_cleanup["targets"])
                self.pending_cleanup = None
                self._write_assistant(answer)
                return

            if self.pending_cleanup and question == "确认清理全部":
                answer = execute_cleanup_remote_jobs(self.pending_cleanup["targets"])
                self.pending_cleanup = None
                self._write_assistant(answer)
                return

            if self.pending_cleanup and question in {"取消", "取消清理", "no", "n", "cancel"}:
                self.pending_cleanup = None
                self._write_system("已取消清理。")
                return

            if self._is_cancel_monitor_request(question):
                job_id = extract_job_id(question)
                self._cancel_monitoring(job_id)
                return

            if self._is_monitor_request(question):
                job_id = extract_job_id(question)
                self._start_monitoring(job_id)
                return

            self._write_system("正在处理请求...")
            self.run_worker(
                lambda: self._handle_question_in_worker(question),
                thread=True,
                exclusive=False,
            )

        def _handle_question_in_worker(self, question: str):
            result = self._build_question_result(question)
            self.call_from_thread(self._apply_question_result, result)

        def _build_question_result(self, question: str):
            intent = detect_intent(question)
            result = {
                "answer": "",
                "job_id": None,
                "live_log": None,
                "pending_submission": None,
                "pending_cleanup": None,
            }

            try:
                if intent == "submit_job":
                    answer, pending_submission = self._prepare_submit_job(question)
                    result["pending_submission"] = pending_submission
                elif intent == "submit_vasp_job":
                    answer, pending_submission = self._prepare_submit_vasp_job(question)
                    result["pending_submission"] = pending_submission
                elif intent == "register_vasp_job":
                    answer = self._format_operation_result(register_existing_vasp_job_from_text(question))
                elif intent == "generate_sbatch":
                    answer = generate_sbatch_script(question)
                elif intent == "generate_vasp_job":
                    answer = generate_vasp_sbatch_script(question)
                elif intent == "job_status":
                    answer, job_id = self._query_job(question, query_job_status, "状态")
                    result["job_id"] = job_id
                elif intent == "job_output":
                    answer, job_id = self._query_job(question, query_job_output, "输出")
                    result["job_id"] = job_id
                    result["live_log"] = answer[-3000:]
                elif intent == "job_error":
                    answer, job_id = self._query_job(question, query_job_error, "错误日志")
                    result["job_id"] = job_id
                    result["live_log"] = answer[-3000:]
                elif intent == "list_remote_jobs":
                    answer = query_remote_agent_jobs()
                elif intent == "cleanup_remote_job":
                    answer, pending_cleanup = self._prepare_cleanup(question)
                    result["pending_cleanup"] = pending_cleanup
                elif intent == "cleanup_all_remote_jobs":
                    answer, pending_cleanup = self._prepare_cleanup_all()
                    result["pending_cleanup"] = pending_cleanup
                elif intent == "suggest_params":
                    answer = suggest_slurm_parameters(question)
                elif intent == "diagnose_error":
                    answer = self.diagnoser.format_results(self.diagnoser.diagnose(question))
                elif intent == "troubleshoot_job":
                    docs = retrieve(question, self.documents, self.sources)
                    answer = ask_llm(question, docs)
                else:
                    docs = retrieve(question, self.documents, self.sources)
                    answer = ask_llm(question, docs)
            except Exception as error:
                answer = f"请求处理失败: {type(error).__name__}: {error}"

            result["answer"] = answer
            return result

        def _apply_question_result(self, result: dict):
            if result.get("pending_submission") is not None:
                self.pending_submission = result["pending_submission"]

            if result.get("pending_cleanup") is not None:
                self.pending_cleanup = result["pending_cleanup"]

            answer = result.get("answer", "")
            self._write_assistant(answer)
            self._select_latest_job_from_answer(answer)

        def _start_monitoring(self, job_id: str):
            job_id = str(job_id)

            if job_id in self.monitored_job_ids:
                self.active_monitor_index = self.monitored_job_ids.index(job_id)
                self._render_monitor_panel()
                return

            self._write_system(f"正在检查 Job {job_id} 是否还在队列中。")
            self.run_worker(
                lambda: self._validate_monitoring_in_worker(job_id),
                thread=True,
                exclusive=False,
            )

        def _validate_monitoring_in_worker(self, job_id: str):
            try:
                validation = validate_monitorable_job(job_id)
            except Exception as error:
                validation = {
                    "job_id": str(job_id),
                    "monitorable": False,
                    "message": f"检查 Job {job_id} 失败：{type(error).__name__}: {error}",
                }

            snapshot = None
            if validation.get("monitorable"):
                try:
                    snapshot = get_job_monitor_snapshot(job_id, lines=50)
                except Exception:
                    snapshot = None

            self.call_from_thread(self._apply_monitoring_validation, validation, snapshot)

        def _apply_monitoring_validation(self, validation: dict, snapshot: dict | None):
            job_id = str(validation["job_id"])

            if not validation.get("monitorable"):
                self._write_system(validation.get("message") or f"Job {job_id} 无法开始监控。")
                return

            self.current_job_id = job_id

            if job_id not in self.monitored_job_ids:
                self.monitored_job_ids.append(job_id)

            self.monitor_snapshots[job_id] = snapshot
            self.monitor_active[job_id] = True
            self.active_monitor_index = self.monitored_job_ids.index(job_id)
            self._write_system(f"开始监控 Job {job_id}。")
            self._render_monitor_panel()
            self._schedule_monitor_refresh()

        def _cancel_monitoring(self, job_id: str):
            job_id = str(job_id)

            if job_id not in self.monitored_job_ids:
                self._write_system(f"当前没有在监控 Job {job_id}。")
                return

            self._remove_monitored_job(job_id)
            self._render_monitor_panel()
            self._write_system(f"已取消监控 Job {job_id}。")

        def _remove_monitored_job(self, job_id: str):
            if job_id not in self.monitored_job_ids:
                return

            removed_index = self.monitored_job_ids.index(job_id)
            self.monitored_job_ids.remove(job_id)
            self.monitor_snapshots.pop(job_id, None)
            self.monitor_active.pop(job_id, None)

            if not self.monitored_job_ids:
                self.active_monitor_index = 0
            elif self.active_monitor_index > removed_index:
                self.active_monitor_index -= 1
            elif self.active_monitor_index >= len(self.monitored_job_ids):
                self.active_monitor_index = len(self.monitored_job_ids) - 1

        def _schedule_monitor_refresh(self):
            active_job_ids = [
                job_id
                for job_id in self.monitored_job_ids
                if self.monitor_active.get(job_id, True)
            ]

            if not active_job_ids or self.monitor_refresh_running:
                return

            self.monitor_refresh_running = True
            self.run_worker(
                lambda: self._monitor_jobs_in_worker(active_job_ids),
                thread=True,
                exclusive=False,
            )

        def _monitor_jobs_in_worker(self, job_ids):
            snapshots = []

            for job_id in job_ids:
                try:
                    snapshot = get_job_monitor_snapshot(job_id, lines=50)
                except Exception as error:
                    snapshot = {
                        "job_id": str(job_id),
                        "squeue_output": "",
                        "squeue_error": f"{type(error).__name__}: {error}",
                        "sacct_output": "",
                        "sacct_error": "",
                        "accounting_state": None,
                        "is_completed": False,
                        "remote_workdir": None,
                        "log_output": "",
                        "log_error": "",
                        "failure_detected": False,
                    }

                snapshots.append(snapshot)

            self.call_from_thread(self._apply_monitor_snapshots, snapshots)

        def _apply_monitor_snapshots(self, snapshots):
            self.monitor_refresh_running = False

            for snapshot in snapshots:
                job_id = snapshot["job_id"]

                if job_id not in self.monitored_job_ids:
                    continue

                self.monitor_snapshots[job_id] = snapshot

                if snapshot.get("is_failed_terminal") and self.monitor_active.get(job_id, True):
                    self._remove_monitored_job(job_id)
                    if job_id not in self.failure_notices_shown:
                        self.failure_notices_shown.add(job_id)
                        self._write_system(
                            f"Job {job_id} 已失败，已从右侧监控移除。可诊断错误日志。"
                        )
                    continue

                if snapshot.get("is_completed") and self.monitor_active.get(job_id, True):
                    self.monitor_active[job_id] = False
                    self._write_system(
                        f"Job {job_id} 已完成，已停止刷新。右侧保留最终状态和最近日志。"
                    )

                if (
                    snapshot.get("failure_detected")
                    and not snapshot.get("is_completed")
                    and job_id not in self.failure_notices_shown
                ):
                    self.failure_notices_shown.add(job_id)
                    self._write_system(
                        f"Job {job_id} 可能失败或出现异常，可诊断错误日志。"
                    )

            self._render_monitor_panel()

        def _active_monitor_job_id(self):
            if not self.monitored_job_ids:
                return None

            self.active_monitor_index %= len(self.monitored_job_ids)
            return self.monitored_job_ids[self.active_monitor_index]

        def _format_monitor_snapshot(self, snapshot: dict, position: int, total: int):
            remote_workdir = snapshot.get("remote_workdir") or "-"
            squeue_error = snapshot.get("squeue_error", "").strip()
            sacct_error = snapshot.get("sacct_error", "").strip()
            state = snapshot.get("state") or "UNKNOWN"
            elapsed = snapshot.get("elapsed") or "-"

            failure_note = ""
            if snapshot.get("failure_detected") and not snapshot.get("is_completed"):
                failure_note = (
                    "\n\n检测到失败/异常信号。可输入："
                    f"\n读取 {snapshot['job_id']} 的错误日志"
                    "\n或粘贴错误日志让 Agent 诊断。"
                )

            error_note = ""
            if squeue_error:
                error_note += f"\n\nsqueue 错误:\n{squeue_error}"
            if sacct_error:
                error_note += f"\n\nsacct 错误:\n{sacct_error}"

            log_text = snapshot.get("log_output", "").strip()
            log_error = snapshot.get("log_error", "").strip()

            if log_error:
                log_text += f"\n\n读取日志错误:\n{log_error}"

            compact_dir = _compact_remote_dir(remote_workdir)
            output_preview = _last_nonempty_lines(log_text, limit=5) or "还没有找到 stdout/stderr 日志。"
            active_text = "active" if self.monitor_active.get(snapshot["job_id"], True) else "stopped"
            return (
                f"Monitor: {position}/{total} ({active_text})\n"
                f"Job: {snapshot['job_id']}\n"
                f"State: {state}\n"
                f"Elapsed: {elapsed}\n"
                f"Dir: {compact_dir}"
                f"{failure_note}"
                f"{error_note}"
                f"\n\nLast Output:\n{output_preview}"
            )

        def _render_monitor_panel(self):
            job_id = self._active_monitor_job_id()

            if not job_id:
                self.query_one("#monitor", Static).update(
                    "没有监控中的任务。\n\n输入“监控 JOBID”开始监控。"
                )
                return

            snapshot = self.monitor_snapshots.get(job_id)

            if snapshot:
                text = self._format_monitor_snapshot(
                    snapshot,
                    self.active_monitor_index + 1,
                    len(self.monitored_job_ids),
                )
            else:
                text = (
                    f"Monitor: {self.active_monitor_index + 1}/{len(self.monitored_job_ids)} (active)\n"
                    f"Job: {job_id}\n\n"
                    "正在读取 squeue 状态和远端日志..."
                )

            self.query_one("#monitor", Static).update(text)

        def _prepare_submit_job(self, question: str):
            candidates = _extract_local_file_candidates(question)
            paths = _extract_local_file_paths(question)
            invalid_candidates = [
                candidate
                for candidate in candidates
                if not Path(candidate).expanduser().is_file()
            ]

            if invalid_candidates and ("上传" in question or not _has_explicit_run_command(question)):
                return (
                    "没有提交作业，因为这些本地作业文件不存在，无法上传到远端：\n"
                    + "\n".join(f"- {candidate}" for candidate in invalid_candidates)
                    + "\n\n请提供正确的本地路径，例如：\n"
                    "跑 /path/to/monitor_cpu.py，4核，15分钟\n\n"
                    "如果文件已经在远端作业目录里，请明确写运行命令，例如：\n"
                    "帮我提交一个作业运行 python monitor_cpu.py，4核，15分钟",
                    None,
                )

            uploaded_files = _uploaded_files_from_paths(paths)
            submit_request = question
            inferred_command = None
            recommendation_details = []

            if uploaded_files and not extract_command(question):
                inferred_command = _infer_run_command(uploaded_files)

            if inferred_command:
                submit_request = f"{question}\n运行命令: {inferred_command}"

            if uploaded_files:
                recommendation_text, recommendation_details = build_resource_recommendation_text(
                    submit_request,
                    uploaded_files,
                )

                if recommendation_text:
                    submit_request = f"{submit_request}\n{recommendation_text}"

            prepared = prepare_submit_script(submit_request)

            if not prepared["ready"]:
                return prepared["message"], None

            pending_submission = {
                "kind": "slurm",
                "script": prepared["script"],
                "uploaded_files": uploaded_files,
            }

            uploaded_note = ""
            if uploaded_files:
                uploaded_note = "\n\n将上传附件:\n" + "\n".join(
                    f"- {item['name']} ({len(item['content'])} bytes)"
                    for item in uploaded_files
                )

            command_note = f"\n\n推断运行命令: {inferred_command}" if inferred_command else ""
            resource_note = ""
            if recommendation_details:
                resource_note = "\n\nAgent 推荐资源:\n" + "\n".join(
                    f"- {item}" for item in recommendation_details
                )
            answer = (
                f"{prepared['message']}{command_note}{resource_note}{uploaded_note}\n\n"
                "回复“确认提交”或按 Ctrl+S 提交；回复“取消提交”或按 Esc 取消。"
            )
            return answer, pending_submission

        def _prepare_submit_vasp_job(self, question: str):
            prepared = prepare_vasp_submit_script(question)

            if not prepared["ready"]:
                return prepared["message"], None

            pending_submission = {
                "kind": "vasp",
                "script": prepared["script"],
                "source_text": question,
                "uploaded_files": [],
            }
            return (
                f"{prepared['message']}\n\n"
                "回复“确认提交”或按 Ctrl+S 提交；回复“取消提交”或按 Esc 取消。"
            ), pending_submission

        def _submit_pending(self):
            if not self.pending_submission:
                self._write_system("当前没有等待提交的作业。")
                return

            pending = self.pending_submission
            self.pending_submission = None

            try:
                if pending["kind"] == "vasp":
                    result = submit_prepared_vasp_script(
                        pending["script"],
                        pending.get("source_text", ""),
                    )
                else:
                    result = submit_prepared_script(
                        pending["script"],
                        uploaded_files=pending.get("uploaded_files", []),
                    )
                answer = result["answer"]
            except Exception as error:
                answer = f"作业提交失败: {type(error).__name__}: {error}"

            self._write_assistant(answer)
            self._select_latest_job_from_answer(answer)

        def _query_job(self, question: str, func, label: str):
            job_id = extract_job_id(question) or self.current_job_id

            if not job_id:
                return f"请提供 Job ID 后再查询{label}。", None

            return func(job_id), job_id

        def _prepare_cleanup(self, question: str):
            job_id = extract_job_id(question)

            if not job_id:
                return "请提供要清理的 Job ID，例如：清理远端作业 11817627 的文件。", None

            prepared = prepare_cleanup_remote_job(job_id)
            pending_cleanup = prepared if prepared["ready"] else None

            return prepared["message"], pending_cleanup

        def _prepare_cleanup_all(self):
            prepared = prepare_cleanup_all_remote_jobs()
            pending_cleanup = prepared if prepared["ready"] else None

            return prepared["message"], pending_cleanup

        def _format_operation_result(self, result: dict):
            return result.get("message", str(result))

        def action_submit_pending(self):
            self._submit_pending()

        def action_cancel_pending(self):
            if self.pending_submission:
                self.pending_submission = None
                self._write_system("已取消提交。")
            elif self.pending_cleanup:
                self.pending_cleanup = None
                self._write_system("已取消清理。")

        def action_next_monitor(self):
            if not self.monitored_job_ids:
                return

            self.active_monitor_index = (self.active_monitor_index + 1) % len(self.monitored_job_ids)
            self._render_monitor_panel()

        def action_refresh_status(self):
            job_id = self._active_monitor_job_id()

            if not job_id:
                self._write_system("当前没有监控中的 Job。请先输入：监控 JOBID")
                return

            self._schedule_monitor_refresh()
            self._write_system(f"正在刷新监控任务。当前显示 Job {job_id}。")

        def action_copy_last_reply(self):
            if not self.last_assistant_reply:
                self._write_system("还没有可复制的 Agent 回复。")
                return

            copied, error = _copy_to_clipboard(self.last_assistant_reply)

            if copied:
                self._write_system("已复制上一条 Agent 回复。")
            else:
                self._write_system(f"当前环境没有可用剪贴板：{error}")

    HPCAgentTUI().run()
