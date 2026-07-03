# Skills 架构说明

本文档说明 HPC Agent 如何把项目能力组织成可执行的 Skills。在本项目中，Skill 不只是 `SKILL.md` 说明书，而是会进入注册、路由、执行、调试和测试流程的能力模块。

## 1. Skill 定义

每个 Skill 位于：

```text
skills/<skill_name>/SKILL.md
```

`SKILL.md` 顶部 frontmatter 定义该能力的运行契约：

```yaml
name: generate-sbatch
description: Generate a safe Slurm sbatch script for HPC jobs.
type: tool
intents:
  - generate_sbatch
handler: modules.slurm.slurm_assistant.generate_sbatch_script
runtime:
  adapter: question_to_text
metadata:
  version: "0.1"
  author: "HPC Agent"
```

核心字段含义：

- `name`：稳定的 Skill 名称。
- `type`：Skill 类型，目前支持 `tool`、`prompt`、`rule`。
- `intents`：该 Skill 负责处理的路由意图。
- `handler`：实际执行函数或类的 Python dotted path。
- `runtime.adapter`：`SkillExecutor` 使用的执行协议。
- `metadata`：版本、作者、来源仓库等附加信息。

## 2. 执行流程

用户自然语言请求进入 Agent 后，典型流程如下：

```text
用户问题
  -> Router 识别 intent
  -> SkillRegistry 根据 intent 找到对应 Skill
  -> SkillExecutor 根据 runtime.adapter 选择执行协议
  -> 调用 handler
  -> AgentRuntimeResult 返回 answer，并在 data["skill"] 中记录 Skill 信息
```

也就是说，已经 Skill 化的能力不再主要依赖 `agent_runtime.py` 中零散的硬编码分支，而是通过统一注册和统一执行路径运行。

## 3. 核心模块

| 模块 | 文件 | 作用 |
|---|---|---|
| SkillRegistry | `modules/skills/skill_registry.py` | 加载 `SKILL.md`，校验 metadata，建立 intent 到 Skill 的映射 |
| SkillExecutor | `modules/skills/skill_executor.py` | 根据 `runtime.adapter` 执行 Skill |
| AgentRuntime | `modules/core/agent_runtime.py` | 在回答 intent 时优先调用已注册 Skill |
| skill_debug | `tools/skill_debug.py` | 查看 Skill 注册、handler 校验和自然语言路由结果 |
| skill_eval | `tools/skill_eval.py` | 对 intent、Skill、adapter 和安全执行样例做回归评测 |

## 4. Runtime Adapters

`runtime.adapter` 表示该 Skill 在 Agent 运行时应该如何调用。

### `question_to_text`

适用于这种函数形态：

```python
handler(question) -> str
```

已使用该 adapter 的 Skills：

- `generate-sbatch`
- `generate-vasp-job`
- `suggest-params`
- `get-available-resources`
- `vasp-report` 的 runtime wrapper

### `injected_diagnoser`

适用于需要运行时注入诊断器对象的能力：

```python
diagnoser.diagnose(question)
diagnoser.format_results(results)
```

已使用该 adapter 的 Skill：

- `diagnose-error`

### `tool_dispatch`

适用于需要调用项目已有工具分发器的能力：

```python
dispatch_tool_request(question, intent, state=state)
```

已使用该 adapter 的 Skill：

- `inspect-job`

该 adapter 会保留 `job_output` 和 `job_error` 原有的 `live_log` 行为，避免影响 TUI 监控区使用。

### `structured_result`

适用于 handler 返回结构化字典的能力：

```python
handler(question) -> {
  "success": bool,
  "message": str,
  ...
}
```

该 adapter 会使用：

- `runtime.message_field` 作为用户可见回答。
- `runtime.success_field` 作为执行成功标志。
- 完整返回字典作为 `AgentRuntimeResult.data`。

已使用该 adapter 的 Skill：

- `generate-vasp-inputs`

该 adapter 还支持 VASP 输入文件覆盖确认：

```yaml
pending_action: generate_vasp_inputs_overwrite
```

当目标目录已经存在 `INCAR`、`KPOINTS` 或 `POSCAR` 时，Agent 不会直接覆盖，而是生成待确认动作，等待用户回复 `确认覆盖` 或 `覆盖已有配置文件`。

## 5. 当前已注册 Skills

| Skill | Intent(s) | Adapter | 功能 |
|---|---|---|---|
| `generate-sbatch` | `generate_sbatch` | `question_to_text` | 生成普通 Slurm sbatch 脚本 |
| `generate-vasp-job` | `generate_vasp_job` | `question_to_text` | 生成 VASP Slurm 作业脚本 |
| `generate-vasp-inputs` | `generate_vasp_inputs` | `structured_result` | 根据本地 VASP 作业目录中的 `POTCAR` 生成 `INCAR`、`KPOINTS`、`POSCAR` |
| `diagnose-error` | `diagnose_error` | `injected_diagnoser` | 诊断 HPC、Slurm、CUDA、Python、权限、内存等常见错误 |
| `vasp-report` | `generate_vasp_report` | `question_to_text` | 通过报告生成 wrapper 生成 VASP 分析报告 |
| `suggest-params` | `suggest_params` | `question_to_text` | 推荐安全的 Slurm 资源参数 |
| `inspect-job` | `job_status`、`job_output`、`job_error` | `tool_dispatch` | 查询 Slurm 作业状态、stdout、stderr |
| `get-available-resources` | `check_local_resources` | `question_to_text` | 检测本地 CPU、内存、磁盘和 GPU 资源 |

## 6. 外部 Skill 集成

项目已迁移的第一个外部 Skill 来自：

```text
K-Dense-AI/scientific-agent-skills/skills/get-available-resources
```

本项目中的适配位置：

```text
skills/get_available_resources/SKILL.md
modules/skills/resource_detector.py
```

该 Skill 的原始目标是检测计算资源并给出计算策略建议。本项目中的本地适配版会只读检测当前运行环境的 CPU、内存、磁盘和 GPU，并把资源快照写入：

```text
/tmp/hpc-agent/available_resources.json
```

它不会连接远端超算，也不会提交作业。

## 7. 调试命令

校验所有 Skills：

```bash
.venv/bin/python tools/skill_debug.py --validate
```

查看某个 Skill：

```bash
.venv/bin/python tools/skill_debug.py inspect-job --validate
```

查看一句自然语言会触发哪个 Skill：

```bash
.venv/bin/python tools/skill_debug.py --route "读取 11814753 的输出" --validate
```

查看完整路由元信息：

```bash
.venv/bin/python tools/route_debug.py "帮我生成我的vasp作业Al_test的配置文件"
```

## 8. Skill 评测

Skill 回归样例位于：

```text
tests/fixtures/skill_cases.json
```

只评测路由、Skill 和 adapter：

```bash
.venv/bin/python tools/skill_eval.py
```

评测路由并执行安全样例：

```bash
.venv/bin/python tools/skill_eval.py --execute
```

评测内容包括：

- 期望 intent
- 期望 Skill
- 期望 runtime adapter
- 禁止误触发的高风险 intent
- 部分安全执行样例的输出片段

## 9. 当前边界

当前 Skill 覆盖已经证明项目支持：

- 文本生成型 Skill
- 注入服务型 Skill
- 工具分发型 Skill
- 结构化结果型 Skill
- 待确认动作型 Skill
- 外部 scientific skill 适配

真实作业提交、远端清理等高风险流程仍然保留显式确认机制，不建议为了追求“全部 Skill 化”而弱化这些安全边界。
