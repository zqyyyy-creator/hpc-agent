# 外部 MCP Tools 注入

本文说明如何让 HPC Agent 自己作为 MCP Client，连接第三方 MCP Server，并把外部 tools 注入到 HPC Agent 的工具系统里。

这和 `hpc-agent-mcp` 暴露 MCP Server 是两个方向：

- HPC Agent MCP Server：外部客户端调用 HPC Agent。
- 外部 MCP 注入：HPC Agent 调用别人的 MCP Server，并把外部工具变成自己的 `external_<server>_<tool>` 工具。

## 当前能力

已经支持：

- 读取 `config/external_mcp_servers.yaml` 或 `HPC_AGENT_EXTERNAL_MCP_CONFIG` 指定的配置。
- 连接 `stdio` 外部 MCP Server。
- 支持 `streamable_http` 外部 MCP Server。
- 发现外部 MCP tools。
- 按 `allowed_tools` 白名单注入工具。
- 注入后的工具名格式为 `external_<server>_<tool>`。
- 通过 CLI 查看、诊断和调用外部工具。
- 在 `hpc_agent_chat` / TUI 自然语言路径中自动调用匹配的外部只读工具。
- 写入外部 MCP 调用审计日志。

## 配置文件

默认配置文件：

```text
config/external_mcp_servers.yaml
```

也可以用环境变量指定：

```bash
export HPC_AGENT_EXTERNAL_MCP_CONFIG=/path/to/external_mcp_servers.yaml
```

示例：

```yaml
servers:
  filesystem:
    enabled: true
    transport: stdio
    command: npx
    args:
      - -y
      - "@modelcontextprotocol/server-filesystem"
      - /home/qyz/projects/hpc-agent
    timeout_seconds: 20
    risk_level: read_only
    allowed_tools:
      - read_file
      - list_directory
```

字段说明：

- `enabled`：是否启用这个外部 MCP Server。
- `transport`：`stdio` 或 `streamable_http`。
- `command`：stdio server 启动命令。
- `args`：stdio server 参数列表。
- `url`：streamable_http server URL。
- `cwd`：stdio server 工作目录。
- `env`：传给 stdio server 的环境变量。
- `timeout_seconds`：连接和调用超时时间。
- `risk_level`：注入工具风险等级，第一版建议只用 `read_only`。
- `allowed_tools`：允许注入的外部工具白名单。为空时不注入任何工具。

## CLI 使用

检查外部 MCP 配置和连接：

```bash
hpc-agent-mcp-client doctor
```

列出已注入工具：

```bash
hpc-agent-mcp-client list-tools
```

调用工具：

```bash
hpc-agent-mcp-client call external_filesystem_read_file '{"path":"README.md"}'
```

指定配置文件：

```bash
hpc-agent-mcp-client --config /tmp/external_mcp_servers.yaml list-tools
```

## 自然语言调用

配置好外部 filesystem MCP 后，可以在 TUI 或 `hpc_agent_chat` 中说：

```text
读取 README.md
```

HPC Agent 会尝试匹配注入工具，例如：

```text
external_filesystem_read_file
```

如果用户明确写出工具名，也会直接调用：

```text
使用 external_filesystem_read_file {"path":"README.md"}
```

HPC/Slurm/VASP 本地意图仍优先走本地工具。外部 MCP 工具主要用于文件读取、目录查看、外部知识库、内部系统查询等扩展能力。

## 审计日志

默认审计日志：

```text
~/.local/share/hpc-agent/external_mcp_audit.jsonl
```

也可以指定：

```bash
export HPC_AGENT_EXTERNAL_MCP_AUDIT_LOG=/tmp/external_mcp_audit.jsonl
```

每次外部 MCP 调用会记录 server、tool、public_tool、arguments_preview、ok、duration_ms 和 error。敏感字段会脱敏。

## 安全建议

第一版推荐只注入只读工具：

```yaml
allowed_tools:
  - read_file
  - list_directory
```

不要直接注入 `delete_file`、`write_file`、`run_shell_command`、`exec`，以及任何能删除、覆盖、联网写入或执行命令的工具。

如果后续要支持写操作，建议再增加确认机制和独立环境开关。

## 常见问题

### 没有发现工具

检查：

```bash
hpc-agent-mcp-client doctor
```

重点看 `enabled`、`command`、`args` 和 `allowed_tools`。

### 能发现但自然语言不调用

可以直接显式指定工具名测试：

```text
使用 external_filesystem_read_file {"path":"README.md"}
```

如果显式调用成功，说明连接正常，只是自然语言匹配不够明确。

### stdio server 受环境变量影响

可以在配置里显式设置 `env`：

```yaml
env:
  PYTHONPATH: /home/qyz/projects/hpc-agent
```

