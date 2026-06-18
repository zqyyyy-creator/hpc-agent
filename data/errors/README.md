# 错误知识库

这里存放 Agent 的错误诊断知识。用户侧只有一个入口：粘贴日志或输入“诊断作业 JOBID”；代码侧按优先级分层匹配。

## 文件分工

| 文件 | 作用 | 优先级 |
|------|------|--------|
| `real_cases.json` | 真实错误案例库，覆盖整个 Agent 的具体失败场景 | 高 |
| `generic_errors.json` | 通用错误模式库，覆盖 HPC/Slurm/Linux/Python 等常见报错 | 低 |

## 匹配规则

1. 先匹配 `real_cases.json`。
2. 再匹配 `generic_errors.json`。
3. 真实案例会优先显示，因为它包含更具体的证据、原因、修复建议、排查命令和预防方式。
4. 通用错误库作为兜底，用于 OOM、permission denied、command not found、invalid partition 等泛化模式。

## 当前覆盖范围

真实案例库面向整个 Agent，而不是只面向超算本身。优先覆盖这些工作流：

- 配置检查：`.env` 缺字段、SSH key 不存在或权限过宽、本地/远端目录不可写、partition 不可用。
- 普通 Slurm：提交失败、远端目录不可写、作业完成后 `squeue` 查不到、stdout/stderr 读取失败。
- VASP：缺 `POTCAR`、`POTCAR` 无效、POSCAR/POTCAR 不一致、VASP 命令不可执行、MPI 环境未初始化、同名目录旧结果混入、缺 OUTCAR、报告上下文生成失败。
- 同步和分析：远端 output 为空、SFTP/SSH 传输失败、Claude Code 命令不存在、API key/model 配置错误。
- TUI/交互：找不到上一个作业记录、剪贴板不可用、确认状态不匹配。

## 新增真实案例

适合放入 `real_cases.json` 的内容：

- Agent 自己产生或包装过的错误提示。
- VASP/Slurm/配置/API/TUI 等具体工作流里的真实失败。
- 能写出明确证据和下一步排查命令的场景。

推荐使用半自动流程，不建议直接手写整段 JSON：

```text
把这个错误整理成案例：<粘贴真实错误日志>
```

或先粘贴/诊断错误日志，再输入：

```text
把这个错误整理成案例
```

Agent 会生成草稿并进入待确认状态；只有回复“确认”后才会写入 `real_cases.json`。如果草稿不合适，回复“取消”，手动调整后再加入。

半自动入库只负责生成候选案例，不等于完全自动维护。确认前建议检查：

- `patterns` 是否稳定，避免只写过短关键词。
- `suggestions` 是否是可执行建议，而不是泛泛描述。
- `commands` 是否只包含排查命令，不能包含删除、覆盖、格式化等破坏性操作。
- 是否已经脱敏用户名、主机名、本地绝对路径、远端家目录、API key/token、机构内网地址等信息。

每个案例建议包含：

```json
{
  "id": "VASP_REAL_001",
  "domain": "vasp",
  "title": "VASP 缺少 POTCAR",
  "severity": "error",
  "applies_to": ["vasp_input", "vasp_submit", "vasp_run"],
  "confidence": "high",
  "patterns": ["Missing required VASP input file: POTCAR"],
  "evidence": ["stdout/stderr 中出现 POTCAR 缺失"],
  "reason": "VASP 运行必须使用真实 POTCAR。",
  "suggestions": ["把真实 POTCAR 放入本地 VASP 输入目录"],
  "commands": ["ls -lh $HPC_LOCAL_VASP_JOBS_INPUT_DIR/JOB_NAME/POTCAR"],
  "prevention": "提交前检查四个 VASP 必需输入文件。"
}
```

字段约定：

- `severity` 可选：`info`、`warning`、`error`。
- `confidence` 可选：`low`、`medium`、`high`。
- `applies_to` 表示案例适用流程，例如 `config_check`、`slurm_submit`、`vasp_submit`、`vasp_analysis`、`sync`、`tui`。
- `patterns` 应使用稳定日志片段或正则，避免只写过短的普通词。
- `commands` 只能放排查命令，不放 destructive 操作。

## 新增通用错误

适合放入 `generic_errors.json` 的内容：

- 跨工作流都可能出现的通用错误。
- 不依赖某个 Agent 操作上下文的报错。
- 可以通过正则关键词稳定识别的错误类别。

通用库仍应避免写入危险命令；诊断器会过滤明显危险的 `rm -rf` 建议。

## 隐私和安全要求

错误案例可能来自真实超算日志，写入前必须避免保存个人或机构敏感信息：

- 不保存真实 API key、token、cookie、私钥路径或私钥内容。
- 不保存完整个人家目录、用户名、主机名、登录节点地址；必要时替换为 `<user>`、`<host>`、`<path>`。
- 不保存受版权限制的 VASP `POTCAR` 内容；案例中只记录错误现象和文件是否存在。
- 不在建议命令里写破坏性操作，例如 `rm -rf`、格式化磁盘、递归改权限等。
- 真实案例应优先记录“如何确认问题”和“如何避免下次再发生”，而不是记录完整原始日志。
