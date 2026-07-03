---
name: inspect-job
description: Inspect Slurm job status, stdout, and stderr logs through the HPC Agent tool dispatcher.
type: tool
intents:
  - job_status
  - job_output
  - job_error
handler: modules.routing.tool_dispatcher.dispatch_tool_request
runtime:
  adapter: tool_dispatch
metadata:
  version: "0.1"
  author: "HPC Agent"
---

# Inspect Job Skill

This skill lets the HPC Agent inspect existing Slurm jobs without submitting or
modifying anything.

## When This Skill Applies

Use this skill when the user asks to:

- check a Slurm job status
- read recent stdout
- read recent stderr or error logs
- inspect the current or previous job from conversation context

Example requests:

- "查看 11814753 的状态"
- "读取 11814753 的输出"
- "读取 11814753 的错误日志"
- "看刚才那个作业的输出"

## Runtime Integration

This skill uses the project tool dispatcher:

```yaml
runtime:
  adapter: tool_dispatch
handler: modules.routing.tool_dispatcher.dispatch_tool_request
```

At runtime the adapter calls:

```python
dispatch_tool_request(question, intent, state=state)
```

## Safety Rules

1. Read only. Do not submit, cancel, clean, or modify jobs.
2. If the user does not provide a Job ID, use conversation context only when available.
3. If no Job ID or recent job context exists, ask the user to provide the Job ID.
4. Only show bounded log content; do not dump unbounded files.
5. Keep stdout/stderr handling separate from cleanup or resubmission suggestions.

## Output

Return the dispatcher's message directly. For stdout/stderr intents, the runtime
also stores a bounded `live_log` copy in result data for TUI monitor integration.
