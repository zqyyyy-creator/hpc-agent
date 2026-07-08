import logging
import re
import shlex
import shutil
from pathlib import Path

import jieba

from modules.tui.tui_helpers import (
    _copy_to_clipboard,
    _extract_local_file_candidates,
    _extract_local_file_paths,
    _has_ambiguous_local_file_candidate,
    _has_explicit_run_command,
    _infer_run_command,
    _requests_no_upload,
    _resolve_local_file_candidate,
    _is_vasp_long_workflow_request,
    _uploaded_files_from_paths,
)
from modules.tui.tui_formatters import format_failure_next_steps, format_monitor_snapshot
from modules.tui.tui_monitor import (
    active_monitor_job_id,
    active_refresh_job_ids,
    analyzing_workflow_job_ids,
    is_cancel_monitor_request,
    is_monitor_request,
    remove_monitored_job_state,
)
from modules.tui.tui_vasp_workflow import (
    apply_vasp_workflow_analysis_result,
    create_vasp_workflow,
    is_vasp_workflow_waiting_for_terminal,
    mark_vasp_workflow_analyzing,
    update_vasp_workflow_from_snapshot,
)

logger = logging.getLogger(__name__)
jieba.setLogLevel(logging.ERROR)


def _is_hpc_submission_smoke_test_request(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.lower())
    markers = [
        "一键测试超算提交流程",
        "测试超算提交流程",
        "测试提交作业流程",
        "测试提交流程",
        "测试超算能不能提交作业",
        "测试这个超算能不能正常提交作业",
        "一键测试提交",
        "一键最小验证流程",
    ]
    return any(marker in normalized for marker in markers)


def run_textual_cli():
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical, VerticalScroll
        from textual.widgets import Header, Input, Static
    except ModuleNotFoundError:
        print(
            "Textual 依赖尚未安装。\n\n"
            "请先运行:\n"
            "  uv sync\n\n"
            "或手动安装:\n"
            "  .venv/bin/python -m pip install textual\n"
        )
        return

    from modules.knowledge.error_diagnoser import ErrorDiagnoser
    from modules.core.confirmed_actions import execute_confirmed_action
    from modules.slurm.job_query import (
        analyze_vasp_job,
        extract_job_id,
        query_job_error,
        query_job_output,
        query_job_status,
    )
    from modules.core.hpc_config import VASP_LOCAL_OUTPUT_DIR, VASP_REMOTE_INPUT_DIR, VASP_REMOTE_OUTPUT_DIR
    from modules.core.conversation_state import GLOBAL_CONVERSATION_STATE
    from modules.core.agent_runtime import (
        can_answer_intent,
        can_preview_cleanup_intent,
        execute_answer_intent,
        execute_cleanup_preview,
        execute_submit_preview,
    )
    from modules.knowledge.knowledge_base import load_documents
    from modules.core.llm_fallback import handle_llm_fallback
    from modules.routing.router import (
        analyze_intent,
        analyze_plan,
        can_execute_plan_all,
        detect_intent,
        expand_shortcut_command,
        format_route_plan,
        get_clarification,
        parse_plan_step_selection,
        serialize_route_plan,
    )
    from modules.routing.tool_dispatcher import dispatch_tool_request
    from modules.slurm.slurm_assistant import (
        build_resource_recommendation_text,
        extract_command,
    )
    from modules.slurm.slurm_tools import (
        HOST,
        REMOTE_WORKDIR,
        USERNAME,
        get_job_monitor_snapshot,
        run_remote_command,
        validate_monitorable_job,
    )
    from modules.slurm.job_submitter import (
        resolve_vasp_job_input_dir,
        vasp_auto_run_name,
    )
    from modules.slurm.job_cleanup import cleanup_remote_agent_targets

    class HPCAgentTUI(App):
        SELECT_AUTO_SCROLL_LINES = 2
        SELECT_AUTO_SCROLL_SPEED = 18.0

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

        #chat-scroll {
            height: 1fr;
            background: #14181b;
            scrollbar-background: #14181b;
            scrollbar-color: #3cd6b5;
        }

        #chat-log {
            width: 100%;
            padding: 0 1;
            background: #14181b;
            color: #f1f5f2;
        }

        #chat-log:focus {
            background: #14181b;
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
            ("ctrl+y", "copy_selection_or_last_reply", "复制选中"),
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
            self.pending_action = None
            self.current_job_id = None
            self.monitored_job_ids = []
            self.monitor_snapshots = {}
            self.monitor_active = {}
            self.active_monitor_index = 0
            self.monitor_refresh_running = False
            self.failure_notices_shown = set()
            self.vasp_workflows = {}
            self.history = []
            self.last_assistant_reply = None
            self.chat_transcript = []

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static(self._top_text(), id="top-bar")
            with Horizontal(id="body"):
                with Vertical(id="chat-pane"):
                    yield Static("Chat", classes="pane-title")
                    with VerticalScroll(id="chat-scroll"):
                        yield Static("", id="chat-log", markup=False)
                with Vertical(id="right-pane"):
                    yield Static("Job Monitor", classes="pane-title")
                    yield Static("输入“监控 JOBID”开始监控。", id="monitor")
            with Vertical(id="input-bar"):
                yield Input(placeholder="Command HPC Agent...  Ctrl+R 刷新状态 / Ctrl+Y 复制选中/回复 / Ctrl+S 提交", id="command-input")

        def on_mount(self):
            self.documents, self.sources = load_documents()
            self._write_assistant(
                "HPC Agent TUI 已启动。\n\n"
                "中间是对话；右侧是显式 Job 监控区；底部输入命令。\n"
                "输入“监控 JOBID”后，右侧会显示 squeue 状态、远端目录和 stdout/stderr 最近 50 行。"
            )
            self.set_interval(5, self._schedule_monitor_refresh)
            self.query_one("#command-input", Input).focus()

        def _top_text(self):
            return (
                f"HPC: {HOST or '-'}    User: {USERNAME or '-'}    "
                f"Remote: {REMOTE_WORKDIR or '-'}    Keys: Ctrl+R 刷新 / Ctrl+Y 复制选中 / Ctrl+S 提交 / Tab 切换"
            )

        def _write_user(self, text: str):
            self._append_chat(f"你: {text}")

        def _write_assistant(self, text: str):
            self.last_assistant_reply = text
            self._append_chat(f"HPC Agent:\n{text}")

        def _write_system(self, text: str):
            self._append_chat(f"[系统] {text}")

        def _append_chat(self, text: str):
            self.chat_transcript.append(text)
            self.query_one("#chat-log", Static).update("\n\n".join(self.chat_transcript))
            self.call_after_refresh(self.query_one("#chat-scroll", VerticalScroll).scroll_end, animate=False)

        def on_key(self, event):
            if event.key == "tab":
                event.prevent_default()
                event.stop()
                self.action_next_monitor()

        def _is_monitor_request(self, text: str):
            return is_monitor_request(text, extract_job_id(text))

        def _is_cancel_monitor_request(self, text: str):
            return is_cancel_monitor_request(text, extract_job_id(text))

        def _select_latest_job_from_answer(self, answer: str):
            matches = re.findall(r"Job ID:\s*(\d+)", answer)

            if matches:
                GLOBAL_CONVERSATION_STATE.record_job(matches[-1], metadata={"source": "ui_select"})

                if not self.monitored_job_ids:
                    self.current_job_id = matches[-1]

        def on_input_submitted(self, event: Input.Submitted):
            question = event.value.strip()
            event.input.value = ""

            if not question:
                return

            self.history.append(question)
            GLOBAL_CONVERSATION_STATE.remember_turn("user", question)
            self._write_user(question)

            if self.pending_submission and self.pending_submission.get("kind") == "vasp_collision":
                if self._is_vasp_collision_choice(question):
                    self._handle_vasp_collision_choice(question)
                    return

                self.pending_submission = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action("submit")
                self._write_system("已放弃上一个待确认的 VASP 提交，继续处理新问题。")

            if self.pending_submission and GLOBAL_CONVERSATION_STATE.is_confirmation(question):
                self._submit_pending()
                GLOBAL_CONVERSATION_STATE.clear_pending_action("submit")
                return

            if self.pending_submission and GLOBAL_CONVERSATION_STATE.is_cancellation(question):
                self.pending_submission = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action("submit")
                self._write_system("已取消提交。")
                return

            if self.pending_cleanup and GLOBAL_CONVERSATION_STATE.is_confirmation(question):
                action_result = execute_confirmed_action(
                    "cleanup",
                    self.pending_cleanup,
                    state=GLOBAL_CONVERSATION_STATE,
                )
                self.pending_cleanup = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action("cleanup")
                self._write_assistant(action_result.message)
                return

            if self.pending_cleanup and GLOBAL_CONVERSATION_STATE.is_cancellation(question):
                self.pending_cleanup = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action("cleanup")
                self._write_system("已取消清理。")
                return

            if self.pending_action and GLOBAL_CONVERSATION_STATE.is_confirmation(question):
                action_result = execute_confirmed_action(
                    self.pending_action.get("kind", ""),
                    self.pending_action.get("payload") or {},
                    state=GLOBAL_CONVERSATION_STATE,
                )
                kind = self.pending_action.get("kind")
                self.pending_action = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action(kind)
                self._write_assistant(action_result.message)
                return

            if self.pending_action and GLOBAL_CONVERSATION_STATE.is_cancellation(question):
                kind = self.pending_action.get("kind")
                self.pending_action = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action(kind)
                self._write_system("已取消待确认操作。")
                return

            question = expand_shortcut_command(question)

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
            selected_step = parse_plan_step_selection(question)
            if selected_step is not None:
                if selected_step == "all":
                    return self._execute_pending_plan_all()

                plan_step = GLOBAL_CONVERSATION_STATE.get_route_plan_step(selected_step)
                if not plan_step:
                    return {
                        "answer": "当前没有可确认的多步骤计划，或步骤编号不存在。请先发送一个多步骤请求。",
                        "job_id": None,
                        "live_log": None,
                        "pending_submission": None,
                        "pending_cleanup": None,
                        "pending_action": None,
                    }
                question = plan_step.get("route_text") or plan_step.get("text") or question
            else:
                question = expand_shortcut_command(question)

            if _is_hpc_submission_smoke_test_request(question):
                plan = None
                intent = "test_hpc_submission"
                decision = None
            else:
                plan = analyze_plan(question)
                decision = None if plan is not None else analyze_intent(question)
                intent = "multi_step_plan" if plan is not None else decision.intent
            result = {
                "answer": "",
                "job_id": None,
                "live_log": None,
                "pending_submission": None,
                "pending_cleanup": None,
                "pending_action": None,
            }

            try:
                if intent == "multi_step_plan":
                    GLOBAL_CONVERSATION_STATE.record_route_plan(serialize_route_plan(plan))
                    answer = format_route_plan(plan)
                elif intent == "clarify":
                    answer = get_clarification(question)
                elif intent == "submit_job":
                    answer, pending_submission = self._prepare_submit_job(question)
                    result["pending_submission"] = pending_submission
                elif intent == "submit_vasp_job":
                    answer, pending_submission = self._prepare_submit_vasp_job(question)
                    result["pending_submission"] = pending_submission
                elif intent == "test_hpc_submission":
                    runtime_result = execute_submit_preview(
                        question,
                        intent,
                        state=GLOBAL_CONVERSATION_STATE,
                        confirmation_text="\n\n回复“确认提交”或按 Ctrl+S 提交；回复“取消提交”或按 Esc 取消。",
                    )
                    answer = runtime_result.answer
                    result["pending_submission"] = runtime_result.data.get("pending_submission")
                elif intent == "generate_test_file":
                    answer = dispatch_tool_request(
                        question,
                        intent,
                        state=GLOBAL_CONVERSATION_STATE,
                    ).message
                elif intent == "rag_qa" and decision is not None and decision.reason != "fallback_no_rule_matched":
                    runtime_result = execute_answer_intent(
                        question,
                        intent,
                        documents=self.documents,
                        sources=self.sources,
                        diagnoser=self.diagnoser,
                        state=GLOBAL_CONVERSATION_STATE,
                        current_job_id=self.current_job_id,
                    )
                    answer = runtime_result.answer
                elif can_answer_intent(intent) and intent != "rag_qa":
                    runtime_result = execute_answer_intent(
                        question,
                        intent,
                        documents=self.documents,
                        sources=self.sources,
                        diagnoser=self.diagnoser,
                        state=GLOBAL_CONVERSATION_STATE,
                        current_job_id=self.current_job_id,
                    )
                    answer = runtime_result.answer
                    result["job_id"] = runtime_result.data.get("job_id")
                    result["live_log"] = runtime_result.data.get("live_log")
                    result["pending_action"] = runtime_result.data.get("pending_action")
                elif can_preview_cleanup_intent(intent):
                    runtime_result = execute_cleanup_preview(
                        question,
                        intent,
                        state=GLOBAL_CONVERSATION_STATE,
                    )
                    answer = runtime_result.answer
                    result["pending_cleanup"] = runtime_result.data.get("pending_cleanup")
                else:
                    fallback = handle_llm_fallback(
                        question,
                        self.documents,
                        self.sources,
                        self.diagnoser,
                        GLOBAL_CONVERSATION_STATE,
                    )
                    intent = fallback.intent
                    answer = fallback.answer
            except Exception as error:
                logger.exception("TUI request handling failed")
                answer = f"请求处理失败: {type(error).__name__}: {error}"

            result["answer"] = answer
            return result

        def _execute_pending_plan_all(self):
            plan = GLOBAL_CONVERSATION_STATE.pending_route_plan
            if not plan:
                return {
                    "answer": "当前没有可执行的多步骤计划。请先发送一个多步骤请求。",
                    "job_id": None,
                    "live_log": None,
                    "pending_submission": None,
                    "pending_cleanup": None,
                    "pending_action": None,
                }

            if not can_execute_plan_all(plan):
                return {
                    "answer": (
                        "这个计划里包含需要确认或补充信息的步骤，不能一次性全部执行。\n"
                        "请改用“确认1”“确认2”逐步执行。"
                    ),
                    "job_id": None,
                    "live_log": None,
                    "pending_submission": None,
                    "pending_cleanup": None,
                    "pending_action": None,
                }

            answers = []
            last_job_id = None
            live_log = None
            for step in plan.get("steps") or []:
                step_text = step.get("route_text") or step.get("text") or ""
                if not step_text:
                    continue
                step_result = self._build_question_result(step_text)
                answers.append(
                    f"第 {step.get('index')} 步: {step.get('intent')}\n"
                    f"{step_result.get('answer', '')}"
                )
                last_job_id = step_result.get("job_id") or last_job_id
                live_log = step_result.get("live_log") or live_log

                if step_result.get("pending_submission") or step_result.get("pending_cleanup") or step_result.get("pending_action"):
                    return {
                        "answer": (
                            "\n\n---\n\n".join(answers)
                            + "\n\n后续步骤暂停：当前步骤产生了需要确认的操作。"
                        ),
                        "job_id": last_job_id,
                        "live_log": live_log,
                        "pending_submission": step_result.get("pending_submission"),
                        "pending_cleanup": step_result.get("pending_cleanup"),
                        "pending_action": step_result.get("pending_action"),
                    }

            return {
                "answer": "\n\n---\n\n".join(answers),
                "job_id": last_job_id,
                "live_log": live_log,
                "pending_submission": None,
                "pending_cleanup": None,
                "pending_action": None,
            }

        def _apply_question_result(self, result: dict):
            if result.get("pending_submission") is not None:
                self.pending_submission = result["pending_submission"]
                GLOBAL_CONVERSATION_STATE.record_pending_action(
                    "submit",
                    self.pending_submission,
                    "作业提交预览，回复“确认执行”或“确认提交”后执行。",
                )

            if result.get("pending_cleanup") is not None:
                self.pending_cleanup = result["pending_cleanup"]
                GLOBAL_CONVERSATION_STATE.record_pending_action(
                    "cleanup",
                    self.pending_cleanup,
                    "远端清理预览，回复“确认执行”或“确认清理”后执行。",
                )

            if result.get("pending_action") is not None:
                self.pending_action = result["pending_action"]
                GLOBAL_CONVERSATION_STATE.record_pending_action(
                    self.pending_action.get("kind", "action"),
                    self.pending_action.get("payload") or {},
                    self.pending_action.get("description", "待确认操作。"),
                )

            answer = result.get("answer", "")
            GLOBAL_CONVERSATION_STATE.remember_turn("assistant", answer)
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
                logger.exception("Failed to validate monitorable job %s", job_id)
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
                    logger.exception("Failed to fetch initial monitor snapshot for job %s", job_id)
                    snapshot = None

            self.call_from_thread(self._apply_monitoring_validation, validation, snapshot)

        def _apply_monitoring_validation(self, validation: dict, snapshot: dict | None):
            job_id = str(validation["job_id"])

            if not validation.get("monitorable"):
                if self._is_vasp_workflow_waiting_for_terminal(job_id):
                    snapshot = snapshot or {
                        "job_id": job_id,
                        "state": validation.get("state") or validation.get("sacct_state") or "UNKNOWN",
                        "elapsed": validation.get("elapsed"),
                        "accounting_state": validation.get("sacct_state"),
                        "is_completed": validation.get("sacct_state") == "COMPLETED",
                        "is_failed_terminal": validation.get("sacct_state") not in {None, "COMPLETED"},
                        "remote_workdir": None,
                        "log_output": "",
                        "log_error": "",
                        "failure_detected": validation.get("sacct_state") not in {None, "COMPLETED"},
                    }
                    if job_id not in self.monitored_job_ids:
                        self.monitored_job_ids.append(job_id)
                    self.monitor_snapshots[job_id] = snapshot
                    self.monitor_active[job_id] = False
                    self.active_monitor_index = self.monitored_job_ids.index(job_id)
                    self._write_system(
                        f"Job {job_id} 已不在 squeue 中，长流程直接进入同步分析。"
                    )
                    self._trigger_vasp_workflow_analysis(job_id, snapshot)
                    self._render_monitor_panel()
                    return

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

            self.active_monitor_index = remove_monitored_job_state(
                self.monitored_job_ids,
                self.monitor_snapshots,
                self.monitor_active,
                self.active_monitor_index,
                job_id,
            )

        def _schedule_monitor_refresh(self):
            active_job_ids = active_refresh_job_ids(self.monitored_job_ids, self.monitor_active)
            analyzing_job_ids = analyzing_workflow_job_ids(self.monitored_job_ids, self.vasp_workflows)

            if not active_job_ids and analyzing_job_ids:
                self._render_monitor_panel()
                return

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
                    logger.exception("Failed to refresh monitor snapshot for job %s", job_id)
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
                self._update_vasp_workflow_from_snapshot(snapshot)

                if snapshot.get("is_failed_terminal") and self.monitor_active.get(job_id, True):
                    if self._is_vasp_workflow_waiting_for_terminal(job_id):
                        self.monitor_active[job_id] = False
                        self._trigger_vasp_workflow_analysis(job_id, snapshot)
                        continue

                    self._remove_monitored_job(job_id)
                    if job_id not in self.failure_notices_shown:
                        self.failure_notices_shown.add(job_id)
                        self._write_system(
                            f"Job {job_id} 已失败，已从右侧监控移除。\n"
                            "建议下一步：\n"
                            f"{format_failure_next_steps(job_id)}"
                        )
                    continue

                if snapshot.get("is_completed") and self.monitor_active.get(job_id, True):
                    self.monitor_active[job_id] = False
                    self._write_system(
                        f"Job {job_id} 已完成，已停止刷新。右侧保留最终状态和最近日志。"
                    )
                    self._trigger_vasp_workflow_analysis(job_id, snapshot)

                if (
                    snapshot.get("failure_detected")
                    and not snapshot.get("is_completed")
                    and job_id not in self.failure_notices_shown
                ):
                    self.failure_notices_shown.add(job_id)
                    vasp_diagnosis = snapshot.get("vasp_diagnosis") or {}
                    if vasp_diagnosis.get("is_vasp") and vasp_diagnosis.get("severity") in {"error", "warning"}:
                        self._write_system(
                            f"Job {job_id} 的 VASP 诊断发现 {vasp_diagnosis.get('severity')}: "
                            f"{vasp_diagnosis.get('summary')}\n"
                            "建议下一步：\n"
                            f"{format_failure_next_steps(job_id, is_vasp=True)}"
                        )
                        continue
                    self._write_system(
                        f"Job {job_id} 可能失败或出现异常。\n"
                        "建议下一步：\n"
                        f"{format_failure_next_steps(job_id)}"
                    )

            self._render_monitor_panel()

        def _start_vasp_workflow(self, job_id: str):
            job_id = str(job_id)
            self.vasp_workflows[job_id] = create_vasp_workflow(job_id)
            self._write_system(
                f"已启动 VASP 长流程 Job {job_id}：监控 -> 同步输出 -> Claude Code 报告。"
            )
            self._start_monitoring(job_id)

        def _is_vasp_workflow_waiting_for_terminal(self, job_id: str):
            return is_vasp_workflow_waiting_for_terminal(self.vasp_workflows, job_id)

        def _update_vasp_workflow_from_snapshot(self, snapshot: dict):
            update_vasp_workflow_from_snapshot(self.vasp_workflows, snapshot)

        def _trigger_vasp_workflow_analysis(self, job_id: str, snapshot: dict):
            terminal_state = mark_vasp_workflow_analyzing(
                self.vasp_workflows,
                job_id,
                snapshot,
            )
            if terminal_state is None:
                return

            self._write_system(
                f"Job {job_id} 已到达终态 {terminal_state}，开始 VASP 自动分析。"
            )
            self._render_monitor_panel()
            self.run_worker(
                lambda: self._vasp_workflow_analysis_in_worker(job_id),
                thread=True,
                exclusive=False,
            )

        def _vasp_workflow_analysis_in_worker(self, job_id: str):
            try:
                answer = analyze_vasp_job(f"分析 VASP 作业 {job_id}")
                success = "VASP 一键分析完成" in answer
                result = {
                    "job_id": str(job_id),
                    "success": success,
                    "answer": answer,
                    "error": "",
                }
            except Exception as error:
                logger.exception("VASP workflow analysis failed for job %s", job_id)
                result = {
                    "job_id": str(job_id),
                    "success": False,
                    "answer": "",
                    "error": f"{type(error).__name__}: {error}",
                }

            self.call_from_thread(self._apply_vasp_workflow_analysis_result, result)

        def _apply_vasp_workflow_analysis_result(self, result: dict):
            job_id = str(result["job_id"])
            workflow = apply_vasp_workflow_analysis_result(self.vasp_workflows, result)

            if not workflow:
                return

            if result["success"]:
                self._write_assistant(
                    f"VASP 长流程 Job {job_id} 已完成。\n\n{result['answer']}"
                )
            else:
                self._write_assistant(
                    f"VASP 长流程 Job {job_id} 自动分析失败。\n\n{workflow['analysis_answer']}"
                )

            self._render_monitor_panel()

        def _active_monitor_job_id(self):
            job_id = active_monitor_job_id(self.monitored_job_ids, self.active_monitor_index)
            if job_id is not None:
                self.active_monitor_index %= len(self.monitored_job_ids)
            return job_id

        def _render_monitor_panel(self):
            job_id = self._active_monitor_job_id()

            if not job_id:
                self.query_one("#monitor", Static).update(
                    "没有监控中的任务。\n\n输入“监控 JOBID”开始监控。"
                )
                return

            snapshot = self.monitor_snapshots.get(job_id)

            if snapshot:
                text = format_monitor_snapshot(
                    snapshot,
                    self.active_monitor_index + 1,
                    len(self.monitored_job_ids),
                    self.monitor_active,
                    self.vasp_workflows,
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
            no_upload = _requests_no_upload(question)
            paths = [] if no_upload else _extract_local_file_paths(question)
            ambiguous_candidates = [
                candidate
                for candidate in candidates
                if not no_upload and _has_ambiguous_local_file_candidate(candidate)
            ]
            invalid_candidates = [
                candidate
                for candidate in candidates
                if not no_upload
                and _resolve_local_file_candidate(candidate) is None
                and candidate not in ambiguous_candidates
            ]

            if no_upload:
                invalid_candidates = []

            if ambiguous_candidates:
                return (
                    "没有提交作业，因为在当前本地目录下找到多个同名文件，无法安全判断要上传哪一个：\n"
                    + "\n".join(f"- {candidate}" for candidate in ambiguous_candidates)
                    + "\n\n请提供更具体的相对路径或绝对路径，例如：\n"
                    "跑 ./jobs/test.py，4核，15分钟",
                    None,
                )

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

            runtime_result = execute_submit_preview(
                submit_request,
                "submit_job",
                state=GLOBAL_CONVERSATION_STATE,
                uploaded_files=uploaded_files,
                source_text=question,
                inferred_command=inferred_command,
                recommendation_details=recommendation_details,
                pending_kind="slurm",
                confirmation_text="\n\n回复“确认提交”或按 Ctrl+S 提交；回复“取消提交”或按 Esc 取消。",
            )
            prepared = runtime_result.data["prepared"]

            if not prepared["ready"]:
                return runtime_result.answer, None

            return runtime_result.answer, runtime_result.data["pending_submission"]

        def _prepare_submit_vasp_job(self, question: str):
            runtime_result = execute_submit_preview(
                question,
                "submit_vasp_job",
                state=GLOBAL_CONVERSATION_STATE,
                auto_analyze=_is_vasp_long_workflow_request(question),
                confirmation_text="\n\n回复“确认提交”或按 Ctrl+S 提交；回复“取消提交”或按 Esc 取消。",
            )
            prepared = runtime_result.data["prepared"]

            if not prepared["ready"]:
                return runtime_result.answer, None

            pending_submission = runtime_result.data["pending_submission"]
            collision = self._build_vasp_run_collision(question)

            if collision and collision["has_collision"]:
                pending_submission = {
                    "kind": "vasp_collision",
                    "pending_vasp": pending_submission,
                    "collision": collision,
                }
                return self._format_vasp_collision_prompt(collision), pending_submission

            return runtime_result.answer, pending_submission

        def _build_vasp_run_collision(self, question: str):
            resolved = resolve_vasp_job_input_dir(question)
            if not resolved["success"]:
                return None

            local_job_dir = resolved["input_dir"]
            run_name = local_job_dir.name
            local_output_dir = Path(VASP_LOCAL_OUTPUT_DIR).expanduser() / run_name
            remote_input_dir = f"{VASP_REMOTE_INPUT_DIR}/{run_name}" if VASP_REMOTE_INPUT_DIR else None
            remote_output_dir = f"{VASP_REMOTE_OUTPUT_DIR}/{run_name}" if VASP_REMOTE_OUTPUT_DIR else None

            local_output_exists = local_output_dir.exists() and any(local_output_dir.iterdir()) if local_output_dir.is_dir() else local_output_dir.exists()
            remote_status = self._check_remote_vasp_run_dirs([remote_input_dir, remote_output_dir])
            remote_collisions = [
                path
                for path, exists in remote_status.items()
                if exists is True
            ]

            has_collision = bool(local_output_exists or remote_collisions)
            return {
                "has_collision": has_collision,
                "run_name": run_name,
                "auto_run_name": vasp_auto_run_name(run_name),
                "local_job_dir": str(local_job_dir),
                "local_output_dir": str(local_output_dir),
                "local_output_exists": local_output_exists,
                "remote_input_dir": remote_input_dir,
                "remote_output_dir": remote_output_dir,
                "remote_status": remote_status,
                "remote_collisions": remote_collisions,
            }

        def _check_remote_vasp_run_dirs(self, paths):
            paths = [path for path in paths if path]
            if not paths:
                return {}

            command = (
                "for d in "
                + " ".join(shlex.quote(path) for path in paths)
                + "; do [ -e \"$d\" ] && printf 'EXISTS\\t%s\\n' \"$d\" || printf 'MISSING\\t%s\\n' \"$d\"; done"
            )

            try:
                output, error = run_remote_command(command)
                status = {}
                for line in output.splitlines():
                    if line.startswith("EXISTS\t"):
                        status[line.split("\t", 1)[1]] = True
                    elif line.startswith("MISSING\t"):
                        status[line.split("\t", 1)[1]] = False
                if error.strip():
                    self._write_system(f"远端重复目录检查有 stderr：{error.strip()}")
                return status
            except Exception as error:
                logger.exception("Remote VASP collision check failed")
                self._write_system(f"远端重复目录检查失败，仅检查本地输出目录：{type(error).__name__}: {error}")
                return {path: None for path in paths}

        def _format_vasp_collision_prompt(self, collision):
            lines = [
                "检测到同名 VASP 运行目录已经存在，暂不提交。",
                "",
                f"作业输入目录: {collision['local_job_dir']}",
                f"默认 run name: {collision['run_name']}",
                "",
                "已存在/可能冲突:",
            ]

            if collision["local_output_exists"]:
                lines.append(f"- 本地输出目录: {collision['local_output_dir']}")

            for path in collision["remote_collisions"]:
                lines.append(f"- 远端目录: {path}")

            unknown_remote = [
                path
                for path, exists in collision["remote_status"].items()
                if exists is None
            ]
            for path in unknown_remote:
                lines.append(f"- 远端目录未能确认: {path}")

            lines.extend([
                "",
                "请选择下一步:",
                "1. 回复“覆盖旧结果”：先清空同名远端 input/output 和本地 output，再提交。",
                f"2. 回复“自动创建新 run name”：使用 {collision['auto_run_name']} 提交。",
                "3. 回复“取消”：放弃本次提交。",
            ])
            return "\n".join(lines)

        def _is_vasp_collision_choice(self, question: str):
            choice = question.strip().lower().replace(" ", "")
            return (
                GLOBAL_CONVERSATION_STATE.is_cancellation(question)
                or choice in {
                    "1", "2", "3",
                    "覆盖", "覆盖旧结果", "复用", "复用同名目录",
                    "自动创建新runname", "自动创建新run名",
                    "自动创建新目录", "新runname", "新目录",
                    "取消",
                }
            )

        def _handle_vasp_collision_choice(self, question: str):
            pending = self.pending_submission
            collision = pending["collision"]
            choice = question.strip().lower().replace(" ", "")

            if GLOBAL_CONVERSATION_STATE.is_cancellation(question) or choice in {"3", "取消"}:
                self.pending_submission = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action("submit")
                self._write_system("已取消 VASP 提交。")
                return

            if choice in {"1", "覆盖", "覆盖旧结果", "复用", "复用同名目录"}:
                cleaned, message = self._clean_vasp_run_collision(collision)
                self._write_system(message)
                if not cleaned:
                    self.pending_submission = pending
                    return

                self.pending_submission = pending["pending_vasp"]
                self._write_system("已清理旧结果，将使用同名 run name 重新提交。")
                self._submit_pending()
                return

            if choice in {"2", "自动创建新runname", "自动创建新run名", "自动创建新目录", "新runname", "新目录"}:
                next_pending = dict(pending["pending_vasp"])
                next_pending["run_name"] = collision["auto_run_name"]
                self.pending_submission = next_pending
                self._write_system(f"将使用新 run name：{collision['auto_run_name']}")
                self._submit_pending()
                return

            self._write_system("请回复：覆盖旧结果 / 自动创建新 run name / 取消")

        def _clean_vasp_run_collision(self, collision):
            local_output_dir = Path(collision["local_output_dir"]).expanduser()
            removed_local = False

            if local_output_dir.exists():
                try:
                    if local_output_dir.is_dir():
                        shutil.rmtree(local_output_dir)
                    else:
                        local_output_dir.unlink()
                    removed_local = True
                except OSError as error:
                    return False, f"本地输出目录清理失败，未提交：{type(error).__name__}: {error}"

            remote_targets = []
            for root_path in [collision.get("remote_input_dir"), collision.get("remote_output_dir")]:
                if not root_path:
                    continue
                root = Path(root_path)
                remote_targets.append({
                    "kind": "dir",
                    "path": root.name,
                    "remote_workdir": str(root.parent),
                })

            remote_result = None
            if remote_targets:
                remote_result = cleanup_remote_agent_targets(remote_targets)
                if not remote_result.get("success"):
                    return (
                        False,
                        "远端 input/output 清理失败，未提交。\n"
                        f"错误: {remote_result.get('error') or '未知错误'}"
                    )

            deleted_remote = len(remote_result.get("deleted", [])) if remote_result else 0
            return (
                True,
                "旧 VASP 结果已清理。\n"
                f"- 本地输出目录: {'已删除' if removed_local else '不存在，无需删除'}\n"
                f"- 远端目录目标: {deleted_remote} 个",
            )

        def _submit_pending(self):
            if not self.pending_submission:
                self._write_system("当前没有等待提交的作业。")
                return

            pending = self.pending_submission
            self.pending_submission = None
            result = {}

            try:
                if pending["kind"] == "vasp":
                    action_result = execute_confirmed_action(
                        "submit_vasp",
                        {
                            "script": pending["script"],
                            "source_text": pending.get("source_text", ""),
                            "run_name": pending.get("run_name"),
                        },
                        state=GLOBAL_CONVERSATION_STATE,
                    )
                else:
                    action_result = execute_confirmed_action(
                        "submit",
                        {
                            "script": pending["script"],
                            "uploaded_files": pending.get("uploaded_files", []),
                        },
                        state=GLOBAL_CONVERSATION_STATE,
                    )
                result = action_result.raw or {}
                answer = action_result.message
            except Exception as error:
                logger.exception("Confirmed submission failed")
                answer = f"作业提交失败: {type(error).__name__}: {error}"

            self._write_assistant(answer)
            self._select_latest_job_from_answer(answer)

            if (
                pending.get("kind") == "vasp"
                and pending.get("auto_analyze")
                and result.get("success")
                and result.get("job_id")
            ):
                self._start_vasp_workflow(result["job_id"])

        def _query_job(self, question: str, func, label: str):
            intent_by_func = {
                query_job_status: "job_status",
                query_job_output: "job_output",
                query_job_error: "job_error",
            }
            intent = intent_by_func.get(func)

            if intent:
                if self.current_job_id and not extract_job_id(question):
                    GLOBAL_CONVERSATION_STATE.record_job(self.current_job_id, metadata={"source": "ui_context"})

                result = dispatch_tool_request(
                    question,
                    intent,
                    state=GLOBAL_CONVERSATION_STATE,
                )
                job_id = result.data.get("job_id") if result.success else None
                return result.message, job_id

            job_id = extract_job_id(question) or self.current_job_id

            if not job_id:
                return f"请提供 Job ID 后再查询{label}。", None

            return func(job_id), job_id

        def action_submit_pending(self):
            self._submit_pending()

        def action_cancel_pending(self):
            if self.pending_submission:
                self.pending_submission = None
                self._write_system("已取消提交。")
            elif self.pending_cleanup:
                self.pending_cleanup = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action("cleanup")
                self._write_system("已取消清理。")
            elif self.pending_action:
                kind = self.pending_action.get("kind")
                self.pending_action = None
                GLOBAL_CONVERSATION_STATE.clear_pending_action(kind)
                self._write_system("已取消待确认操作。")

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

        def action_copy_selection_or_last_reply(self):
            selected_text = self.screen.get_selected_text()
            text_to_copy = selected_text.strip() if selected_text else ""
            source = "选中文本"

            if not text_to_copy:
                if not self.last_assistant_reply:
                    self._write_system("还没有可复制的选中文本或 Agent 回复。")
                    return
                text_to_copy = self.last_assistant_reply
                source = "上一条 Agent 回复"

            copied, error = _copy_to_clipboard(text_to_copy)

            if copied:
                self._write_system(f"已复制{source}。")
            else:
                try:
                    self.copy_to_clipboard(text_to_copy)
                    self._write_system(f"已通过终端剪贴板复制{source}。")
                except Exception as copy_error:
                    logger.exception("Clipboard copy failed")
                    self._write_system(
                        "当前环境没有可用剪贴板："
                        f"{error}; terminal clipboard: {type(copy_error).__name__}: {copy_error}"
                    )

    HPCAgentTUI().run()
