# 将 HPC Agent MCP 接入 ChatGPT Web

这是一个客户端专项示例。HPC Agent MCP 服务是通用 MCP 服务，不是 ChatGPT 专用协议；其他 MCP 客户端也可以通过 STDIO 或 Streamable HTTP 接入。

ChatGPT Web 不能直接启动本地 STDIO 命令，因此需要把本地 MCP 服务暴露成 HTTPS URL，再把这个 URL 填到 ChatGPT 的应用/连接器配置里。

## 1. 启动 Streamable HTTP MCP

在项目目录或已安装环境中启动：

```bash
hpc-agent-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

本地 MCP 地址是：

```text
http://127.0.0.1:8000/mcp
```

连接期间需要保持这个进程运行。

## 2. 暴露 HTTPS 地址

浏览器端 ChatGPT 需要公网 HTTPS。可以使用 Cloudflare Tunnel 或 ngrok。

Cloudflare quick tunnel 示例：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

得到公网地址后，在末尾追加 `/mcp`：

```text
https://YOUR-TUNNEL.trycloudflare.com/mcp
```

然后重启 MCP 服务，并放行 tunnel 的 Host：

```bash
hpc-agent-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --path /mcp \
  --allowed-host YOUR-TUNNEL.trycloudflare.com
```

ngrok 也是同样逻辑：

```bash
ngrok http 8000
```

```bash
hpc-agent-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --path /mcp \
  --allowed-host YOUR-NGROK-ID.ngrok.app
```

## 3. 在 ChatGPT 中创建连接

在 ChatGPT Web 中进入：

```text
Settings
Developer mode
Create app / plugin / MCP server
```

填写：

```text
Name: HPC Agent
MCP server URL: https://YOUR-TUNNEL.trycloudflare.com/mcp
Auth: 无授权
```

保存后，新开一个对话，并在工具选择器中选择 HPC Agent。

应用名称和描述建议参考：

```text
docs/mcp_docs/MCP_CHATGPT_APP_METADATA.md
```

描述很重要，ChatGPT 会结合 app description 和 tool docstring 判断什么时候自动调用 HPC Agent。

## 4. 安全测试提示词

先测试只读和预览：

```text
检查当前 HPC 配置
```

```text
查看 amd_test 分区相关信息
```

```text
生成 Slurm 脚本预览：command: hostname nodes: 1 time: 00:05:00 partition: amd_test
```

普通对话优先用自然语言，不需要每次都说具体工具名。`hpc_agent_chat` 是高层入口，会复用 TUI 的意图路由。

## 5. 写入和危险操作保护

默认以下工具不会真正执行：

```text
hpc_submit_prepared_job
vasp_sync_output
hpc_execute_cleanup
```

控制测试中允许提交或 VASP 同步：

```bash
export HPC_AGENT_MCP_ENABLE_WRITE=1
```

控制测试中允许远端清理：

```bash
export HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1
```

即使开启环境变量，MCP 调用仍必须带 `confirm=true`。

## 6. 审计日志

预览、写本地文件、执行和清理类工具会写入审计日志：

```text
~/.local/share/hpc-agent/mcp_audit.jsonl
```

自定义路径：

```bash
export HPC_AGENT_MCP_AUDIT_LOG=/path/to/mcp_audit.jsonl
```

## 常见问题

- ChatGPT 无法连接：确认 URL 以 `/mcp` 结尾。
- 服务日志出现 `Invalid Host header` 或返回 `421`：重启时加入 `--allowed-host YOUR-TUNNEL-HOST`。
- 浏览器提示服务不可达：确认本地 `hpc-agent-mcp` 进程还在运行。
- 工具拒绝执行：检查 `confirm=true` 和对应的 `HPC_AGENT_MCP_ENABLE_*` 环境变量。
- 远端 HPC 操作失败：先在本地运行 `hpc-agent-check` 检查 `.env`、SSH、远端目录和分区配置。
