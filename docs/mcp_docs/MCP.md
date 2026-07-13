# HPC Agent MCP 服务

`hpc-agent-mcp` 会把 HPC Agent 的部分能力暴露为标准 MCP 服务。它支持 STDIO 和 Streamable HTTP 两种传输方式，可以被 ChatGPT Web、Claude Desktop、Cursor、Codex 或其他 MCP 客户端接入。

MCP 接口遵循“先预览、再确认、后执行”的安全策略。脚本生成、VASP 作业准备和清理目标生成默认只是预览；真实提交、同步和删除都需要显式确认和服务端安全开关。

## 可用工具

| 工具 | 风险级别 | 用途 |
| --- | --- | --- |
| `hpc_check_install` | read_only | 检查安装资源、命令入口、RAG 文档和 skills 是否完整。 |
| `hpc_check_config` | read_only | 检查 `.env`、本地路径、SSH/HPC 配置、远端目录、VASP 命令和分区可用性。 |
| `hpc_get_cluster_info` | read_only | 查询内置集群、Slurm、GPU、存储、环境模块和 VASP 文档。 |
| `hpc_list_skills` | read_only | 列出内置和外部 hpc-agent skills。 |
| `hpc_agent_chat` | mixed | 高层自然语言入口，复用 TUI 路由和上下文，普通对话优先使用。 |
| `hpc_generate_sbatch` | write_preview | 根据自然语言生成 Slurm sbatch 脚本预览，不提交。 |
| `hpc_generate_sbatch_structured` | write_preview | 根据结构化参数生成 Slurm sbatch 脚本预览，不提交。 |
| `hpc_submit_prepared_job` | write_execute | 提交已经审核过的 Slurm 或 VASP 脚本；需要确认和写入开关。 |
| `hpc_prepare_vasp_job` | write_preview | 根据自然语言或本地 VASP 输入目录生成 VASP Slurm 作业预览，不提交、不上传。 |
| `hpc_prepare_vasp_job_structured` | write_preview | 根据本地输入目录和资源参数生成 VASP Slurm 作业预览，不提交、不上传。 |
| `vasp_generate_inputs` | write_local | 在本地 VASP 作业目录中根据 `POTCAR` 和描述生成 `INCAR`、`KPOINTS`、`POSCAR`。 |
| `vasp_generate_inputs_structured` | write_local | 根据结构化材料/计算参数生成本地 VASP 输入文件。 |
| `vasp_analyze_local_result` | write_local | 分析本地 VASP 输出目录，在 `analysis/` 下生成报告上下文和图表元数据。 |
| `vasp_analyze_local_result_structured` | write_local | 根据明确的本地路径分析 VASP 输出目录。 |
| `vasp_sync_output` | write_execute | 将远端 VASP 输出同步到本地；需要确认和写入开关。 |
| `vasp_sync_output_structured` | write_execute | 根据明确 Slurm job id 同步 VASP 输出；需要确认和写入开关。 |
| `hpc_query_job` | read_only | 根据 job id 查询 Slurm 作业状态、输出或错误日志。 |
| `hpc_query_job_structured` | read_only | 根据明确的 `job_id` 和 `query_type` 查询作业。 |
| `hpc_prepare_cleanup` | destructive_preview | 预览远端清理目标，不删除文件。 |
| `hpc_prepare_cleanup_structured` | destructive_preview | 根据清理类型、job id/selector 和范围预览清理目标，不删除文件。 |
| `hpc_execute_cleanup` | destructive | 删除已经预览过的远端目标；需要确认和危险操作开关。 |

## 可用资源

| Resource | MIME type | 用途 |
| --- | --- | --- |
| `hpc-agent://docs/user-guide` | `text/markdown` | 用户手册。 |
| `hpc-agent://cluster/info` | `text/plain` | 内置集群和 HPC 知识文档。 |
| `hpc-agent://skills` | `application/json` | 已加载 skills 和被跳过的外部 skills。 |
| `hpc-agent://config/status` | `application/json` | 脱敏后的配置和环境检查结果。 |
| `hpc-agent://jobs/recent` | `application/json` | 最近登记的 Slurm/VASP 作业。 |
| `hpc-agent://capabilities` | `application/json` | MCP 能力、风险级别、安全开关和推荐客户端行为。 |
| `hpc-agent://schema/tools` | `application/json` | 统一返回结构和结构化工具参数 schema。 |
| `hpc-agent://deployment/status` | `application/json` | 健康检查、审计路径和部署相关环境变量。 |
| `hpc-agent://security/policy` | `application/json` | 安全策略、确认机制、危险操作规则和审计行为。 |
| `hpc-agent://examples` | `application/json` | 自然语言、结构化和受保护工具调用示例。 |

## 可用 Prompts

| Prompt | 用途 |
| --- | --- |
| `submit-slurm-job` | 指导安全的 Slurm 脚本生成和确认提交流程。 |
| `diagnose-slurm-error` | 指导 Slurm 作业状态、输出和错误日志诊断。 |
| `prepare-vasp-job` | 指导 VASP 输入生成和作业预览。 |
| `analyze-vasp-result` | 指导本地 VASP 结果分析。 |
| `cleanup-remote-job` | 指导清理预览和受保护清理执行。 |
| `hpc-agent-natural-language` | 指导通用客户端优先使用 `hpc_agent_chat`。 |
| `hpc-agent-submit-safe-workflow` | 指导预览优先、确认后提交。 |
| `hpc-agent-vasp-full-workflow` | 指导 VASP 输入、提交、同步和分析完整流程。 |
| `hpc-agent-debug-connection` | 指导 HTTP、tunnel 和 Host header 连接排查。 |

## 统一返回格式

MCP 工具会返回稳定 envelope，同时保留工具专属字段，兼容简单客户端和结构化客户端：

```json
{
  "ok": true,
  "risk": "read_only",
  "message": "完整可读输出",
  "reply": "较短的助手回复",
  "plain_text": "最通用的文本字段",
  "data": {},
  "next_step": "可选下一步建议",
  "requires_confirmation": false,
  "required_env": null,
  "schema_version": "2026-07-13"
}
```

简单客户端可以显示 `plain_text`；对话型客户端可以优先使用 `reply`；自动化客户端可以读取 `data`。

## 结构化工具示例

当客户端已经知道明确参数时，使用结构化工具，避免自然语言解析误差：

```json
{
  "tool": "hpc_generate_sbatch_structured",
  "arguments": {
    "command": "hostname",
    "nodes": 1,
    "time_limit": "00:05:00",
    "partition": "amd_test",
    "cpus_per_task": 1,
    "job_name": "hostname_test"
  }
}
```

```json
{
  "tool": "hpc_prepare_vasp_job_structured",
  "arguments": {
    "local_input_dir": "/home/qyz/vasp-jobs-input/si_static_test",
    "nodes": 1,
    "time_limit": "01:00:00",
    "partition": "amd_test"
  }
}
```

```json
{
  "tool": "vasp_generate_inputs_structured",
  "arguments": {
    "job_name": "si_static_test",
    "element": "Si",
    "calculation_type": "static",
    "encut": 400,
    "kpoints": [2, 2, 2]
  }
}
```

如果请求依赖上下文，例如“提交刚才那个”“查看上一个作业”，应使用 `hpc_agent_chat`。

## 本地运行 STDIO

```bash
hpc-agent-mcp
```

STDIO 由 MCP 客户端管理 JSON-RPC 流，不要把普通文本 pipe 给这个进程。

## 本地运行 Streamable HTTP

浏览器客户端或 tunnel 场景使用 HTTP：

```bash
hpc-agent-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

本地端点：

```text
http://127.0.0.1:8000/mcp
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

## 通过公网 tunnel 接入

浏览器客户端需要公网 HTTPS。示例：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

得到公网域名后，重启 MCP 服务并放行 Host：

```bash
hpc-agent-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --path /mcp \
  --allowed-host YOUR-TUNNEL.trycloudflare.com
```

客户端 URL 填：

```text
https://YOUR-TUNNEL.trycloudflare.com/mcp
```

ChatGPT Web 详细步骤见：

```text
docs/mcp_docs/MCP_CHATGPT_WEB.md
```

通用 MCP 客户端说明见：

```text
docs/mcp_docs/MCP_CLIENTS.md
```

部署和 systemd 说明见：

```text
docs/mcp_docs/MCP_DEPLOYMENT.md
```

## 自然语言用法

普通对话优先使用 `hpc_agent_chat`，不要要求用户每次都说“调用某某工具”。示例：

```text
检查当前 HPC 配置
生成 Slurm 脚本预览：command: hostname nodes: 1 time: 00:05:00 partition: amd_test
查看最近作业
分析 VASP 作业 123456
```

`hpc_agent_chat` 可以生成预览、查询作业、诊断日志、路由 VASP 请求和回答内置 HPC 知识问题。它不会绕过安全开关：真实提交、同步和清理仍需要专用受保护工具、`confirm=true` 和对应环境变量。

## Codex CLI 示例

```bash
codex mcp add hpc-agent -- /home/your-user/.local/bin/hpc-agent-mcp
codex mcp list
```

## 桌面客户端配置示例

Claude Desktop、Cursor、ChatGPT Desktop 或类似客户端可以添加 STDIO MCP 服务：

```json
{
  "mcpServers": {
    "hpc-agent": {
      "command": "/home/your-user/.local/bin/hpc-agent-mcp"
    }
  }
}
```

保存配置后重启客户端。

## 安全说明

- Slurm 脚本生成默认只是预览。
- VASP 作业脚本生成默认只是预览。
- VASP 输入生成和本地结果分析会在选定的本地目录写文件。
- 作业提交和 VASP 输出同步需要 `confirm=true` 与 `HPC_AGENT_MCP_ENABLE_WRITE=1`。
- 远端清理需要 `confirm=true` 与 `HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1`。
- API key、token 等敏感字段会在结构化结果和审计中脱敏。
- 远端 Slurm 查询仍然使用用户本机 hpc-agent 的 `.env` 和 SSH 配置。
- 写预览、写本地、执行和危险操作都会记录审计日志。

## 执行开关

默认关闭写入和危险执行：

```bash
unset HPC_AGENT_MCP_ENABLE_WRITE
unset HPC_AGENT_MCP_ENABLE_DESTRUCTIVE
```

受控测试中允许作业提交或 VASP 输出同步：

```bash
export HPC_AGENT_MCP_ENABLE_WRITE=1
```

受控测试中允许远端清理：

```bash
export HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1
```

即使环境变量已开启，MCP 调用仍必须传入 `confirm=true`。

## 审计日志

MCP 写入和危险工具会记录 JSON Lines 审计日志，默认路径：

```text
~/.local/share/hpc-agent/mcp_audit.jsonl
```

自定义路径：

```bash
export HPC_AGENT_MCP_AUDIT_LOG=/path/to/mcp_audit.jsonl
```

审计记录包含时间、工具名、风险级别、脱敏参数、成功状态和确认/权限状态。

## 建议冒烟测试

用 MCP inspector 或客户端列出工具后，依次测试：

```text
hpc_check_install
hpc_agent_chat(message="生成 Slurm 脚本预览：command: hostname nodes: 1 time: 00:05:00 partition: amd_test")
hpc_get_cluster_info(query="amd_test partition")
hpc_list_skills
hpc_generate_sbatch_structured(command="hostname", nodes=1, time_limit="00:05:00", partition="amd_test")
hpc_prepare_vasp_job_structured(local_input_dir="/home/qyz/vasp-jobs-input/si_static_test", nodes=1, time_limit="01:00:00", partition="amd_test")
vasp_analyze_local_result_structured(local_job_dir="/home/qyz/vasp-jobs-output/si_static_test")
hpc_query_job_structured(job_id="123456", query_type="status")
hpc_prepare_cleanup_structured(cleanup_type="job", job_id="123456", scope="all")
```

Slurm 和 VASP 预览工具应该返回脚本或预览信息，不应提交作业或上传文件。
