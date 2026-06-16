from dataclasses import dataclass, field
from datetime import datetime, timezone
import re


LAST_JOB_REFERENCE_VALUES = {
    "",
    "last",
    "latest",
    "previous",
    "recent",
    "刚才",
    "上一个",
    "上个",
    "最近",
    "它",
    "这个作业",
    "那个作业",
    "前一个",
}
VASP_KIND_ALIASES = {"vasp", "VASP"}
TEST_KIND_ALIASES = {"test", "测试", "测试作业"}
SLURM_KIND_ALIASES = {"slurm", "普通", "普通作业", "job"}
GENERIC_CONFIRMATIONS = {
    "确认", "确认执行", "执行", "继续", "确定", "可以", "好的", "好",
    "确认提交", "确认清理", "确认清理全部",
    "yes", "y", "ok", "okay", "submit", "confirm",
}
GENERIC_CANCELLATIONS = {
    "取消", "取消执行", "取消提交", "取消清理", "不用", "不要", "算了",
    "no", "n", "cancel",
}


@dataclass
class ConversationState:
    last_job_id: str | None = None
    last_vasp_job_id: str | None = None
    last_remote_workdir: str | None = None
    last_tool_call: dict | None = None
    last_generated_file: str | None = None
    pending_route_plan: dict | None = None
    pending_action: dict | None = None
    conversation_turns: list[dict] = field(default_factory=list)
    recent_jobs: list[dict] = field(default_factory=list)

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def _normalize_kind(self, metadata: dict | None = None):
        metadata = metadata or {}
        raw_kind = metadata.get("kind") or metadata.get("type") or "slurm"
        kind = str(raw_kind).lower()

        if kind in {"vasp"} or str(metadata.get("type", "")).lower() == "vasp":
            return "vasp"

        if str(raw_kind) in TEST_KIND_ALIASES or kind in {"test", "hpc_test", "test_job"}:
            return "test"

        return "slurm"

    def _normalize_source(self, metadata: dict | None = None):
        metadata = metadata or {}
        return metadata.get("source") or "unknown"

    def record_job(
        self,
        job_id: str | None,
        remote_workdir: str | None = None,
        metadata: dict | None = None,
        *,
        kind: str | None = None,
        source: str | None = None,
    ):
        if not job_id:
            return

        metadata = dict(metadata or {})

        if kind:
            metadata["kind"] = kind

        if source:
            metadata["source"] = source

        normalized_kind = self._normalize_kind(metadata)
        normalized_source = self._normalize_source(metadata)
        created_at = metadata.pop("created_at", None) or self._now()
        job = {
            "job_id": str(job_id),
            "kind": normalized_kind,
            "remote_workdir": remote_workdir,
            "created_at": created_at,
            "source": normalized_source,
            "metadata": dict(metadata),
            **metadata,
        }
        self.last_job_id = str(job_id)

        if normalized_kind == "vasp":
            self.last_vasp_job_id = str(job_id)

        if remote_workdir:
            self.last_remote_workdir = remote_workdir

        self.recent_jobs = [
            existing
            for existing in self.recent_jobs
            if existing.get("job_id") != str(job_id)
        ]
        self.recent_jobs.insert(0, job)
        self.recent_jobs = self.recent_jobs[:10]

    def jobs(self, *, kind: str | None = None, source: str | None = None):
        jobs = self.recent_jobs

        if kind:
            normalized_kind = self._normalize_kind({"kind": kind})
            jobs = [job for job in jobs if job.get("kind") == normalized_kind]

        if source:
            jobs = [job for job in jobs if job.get("source") == source]

        return jobs

    def get_recent_job(self, *, kind: str | None = None, source: str | None = None, index: int = 0):
        jobs = self.jobs(kind=kind, source=source)

        if index < 0 or index >= len(jobs):
            return None

        return jobs[index]

    def _extract_ordinal_index(self, text: str | None):
        if not text:
            return 0

        normalized = str(text).lower().replace(" ", "")
        ordinal_map = {
            "第一个": 0,
            "第1个": 0,
            "第1": 0,
            "first": 0,
            "第二个": 1,
            "第2个": 1,
            "第2": 1,
            "second": 1,
            "第三个": 2,
            "第3个": 2,
            "第3": 2,
            "third": 2,
        }

        for marker, index in ordinal_map.items():
            if marker in normalized:
                return index

        match = re.search(r"第(\d+)个?", normalized)

        if match:
            return max(0, int(match.group(1)) - 1)

        return 0

    def infer_kind_from_text(self, text: str | None):
        if not text:
            return None

        normalized = str(text).lower().replace(" ", "")

        if any(alias.lower() in normalized for alias in VASP_KIND_ALIASES):
            return "vasp"

        if any(alias.lower() in normalized for alias in TEST_KIND_ALIASES):
            return "test"

        if any(alias.lower() in normalized for alias in SLURM_KIND_ALIASES):
            return "slurm"

        return None

    def resolve_job_reference(self, value: str | None = None, *, kind: str | None = None, source: str | None = None):
        normalized_value = str(value).strip() if value is not None else ""
        lowered_value = normalized_value.lower()

        if normalized_value and lowered_value not in LAST_JOB_REFERENCE_VALUES:
            if re.fullmatch(r"[A-Za-z0-9_.:-]+", normalized_value) and any(char.isdigit() for char in normalized_value):
                return normalized_value

        inferred_kind = kind or self.infer_kind_from_text(value)
        index = self._extract_ordinal_index(value)
        job = self.get_recent_job(kind=inferred_kind, source=source, index=index)

        if job:
            return job.get("job_id")

        if inferred_kind == "vasp":
            return self.last_vasp_job_id

        return self.last_job_id

    def resolve_job_id(self, value: str | None, *, kind: str | None = None, source: str | None = None):
        return self.resolve_job_reference(value, kind=kind, source=source)

    def resolve_vasp_job_id(self, value: str | None):
        return self.resolve_job_reference(value, kind="vasp") or self.last_job_id

    def context_summary(self) -> str:
        """生成当前会话上下文的简短摘要，供 LLM 意图分类使用。"""
        parts = []

        if self.pending_action:
            parts.append(
                "当前有一个待确认动作: "
                f"{self.pending_action.get('kind')} - {self.pending_action.get('description', '')}"
            )

        if self.pending_route_plan:
            parts.append("当前有一个待确认的多步骤计划。")

        if not self.recent_jobs:
            parts.append("当前会话还没有记录任何作业。")
            return "\n".join(parts)

        kind_labels = {"vasp": "VASP", "test": "测试", "slurm": "普通"}
        parts.append("当前会话已记录的作业（按时间倒序）：")

        for i, job in enumerate(self.recent_jobs[:10]):
            kind_label = kind_labels.get(job.get("kind"), "未知")
            parts.append(
                f"- 第{i + 1}个: Job ID {job['job_id']} ({kind_label}), "
                f"目录: {job.get('remote_workdir', '未知')}"
            )

        return "\n".join(parts)

    def answer_context_summary(self, max_turns: int = 20, max_chars_per_turn: int = 600) -> str:
        """生成给知识库问答使用的上下文摘要。"""
        parts = [self.context_summary()]

        if self.conversation_turns:
            parts.append("最近对话（按时间顺序）：")

            for turn in self.conversation_turns[-max_turns:]:
                role = "用户" if turn.get("role") == "user" else "助手"
                content = str(turn.get("content", "")).strip()

                if len(content) > max_chars_per_turn:
                    content = content[:max_chars_per_turn].rstrip() + "..."

                if content:
                    parts.append(f"- {role}: {content}")

        return "\n".join(part for part in parts if part)

    def record_route_plan(self, plan: dict | None):
        self.pending_route_plan = plan
        if plan:
            self.record_pending_action(
                "route_plan",
                {"plan": plan},
                "多步骤计划，回复“确认1”执行某一步，或在安全时回复“全部执行”。",
            )

    def clear_route_plan(self):
        self.pending_route_plan = None
        if self.pending_action and self.pending_action.get("kind") == "route_plan":
            self.pending_action = None

    def get_route_plan_step(self, index: int):
        if not self.pending_route_plan:
            return None

        steps = self.pending_route_plan.get("steps") or []
        if index < 1 or index > len(steps):
            return None

        return steps[index - 1]

    def record_pending_action(self, kind: str, payload: dict | None = None, description: str = ""):
        self.pending_action = {
            "kind": kind,
            "payload": payload or {},
            "description": description,
            "created_at": self._now(),
        }

    def clear_pending_action(self, kind: str | None = None):
        if kind is None or (self.pending_action and self.pending_action.get("kind") == kind):
            self.pending_action = None

    def remember_turn(self, role: str, content: str, metadata: dict | None = None):
        if not content:
            return

        self.conversation_turns.append({
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "created_at": self._now(),
        })
        self.conversation_turns = self.conversation_turns[-20:]

    def is_confirmation(self, text: str):
        return str(text).lower().replace(" ", "") in GENERIC_CONFIRMATIONS

    def is_cancellation(self, text: str):
        return str(text).lower().replace(" ", "") in GENERIC_CANCELLATIONS


GLOBAL_CONVERSATION_STATE = ConversationState()
