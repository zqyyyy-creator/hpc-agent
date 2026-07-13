# MCP 部署说明

本文说明如何把开发态 MCP 服务部署成可重复启动的本地服务，供 ChatGPT Web、Claude Desktop、Cursor、Codex 或其他 MCP 客户端使用。

## 部署相关文件

- `scripts/start_mcp_http.sh`：一键启动 Streamable HTTP MCP 服务。
- `packaging/systemd/hpc-agent-mcp.service`：用户级 systemd 服务模板。
- `.env.example`：包含 MCP host、port、path、allowed host、日志、审计和安全开关变量。
- `/health`：HTTP 健康检查接口。

## 配置 `.env`

如果还没有配置文件，可以从模板复制：

```bash
cp .env.example .env
```

普通 HPC 配置之外，MCP 部署常用变量如下：

```bash
HPC_AGENT_MCP_HOST=127.0.0.1
HPC_AGENT_MCP_PORT=8000
HPC_AGENT_MCP_PATH=/mcp
HPC_AGENT_MCP_ALLOWED_HOST=hpc-agent.example.com
HPC_AGENT_LOG_DIR=/home/qyz/.local/share/hpc-agent/logs
HPC_AGENT_MCP_AUDIT_LOG=/home/qyz/.local/share/hpc-agent/mcp_audit.jsonl
HPC_AGENT_MCP_ENABLE_WRITE=0
HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=0
```

`HPC_AGENT_MCP_ALLOWED_HOST` 填公网 tunnel 或固定域名的 host 部分，不要带 `https://`，也不要带 `/mcp`。

## 一键启动

```bash
cd /home/qyz/projects/hpc-agent
scripts/start_mcp_http.sh
```

这个脚本会：

- 从项目根目录加载 `.env`；
- 启动 `hpc-agent-mcp --transport streamable-http`；
- 创建固定日志目录；
- 将 MCP stdout/stderr 写入 `mcp-http.log`；
- 按 `HPC_AGENT_MCP_AUDIT_LOG` 保存审计日志。

安装版也可以直接运行：

```bash
hpc-agent-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

## 健康检查

本地检查：

```bash
curl http://127.0.0.1:8000/health
```

预期返回：

```json
{"ok":true,"service":"hpc-agent-mcp","transport":"streamable-http","mcp_path":"/mcp"}
```

通过 tunnel 或固定域名检查：

```bash
curl https://hpc-agent.example.com/health
```

如果 `/health` 正常，但客户端连不上 MCP，优先检查客户端 URL 是否以 `/mcp` 结尾。

## 用户级 systemd 服务

安装模板：

```bash
mkdir -p ~/.config/systemd/user
cp packaging/systemd/hpc-agent-mcp.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hpc-agent-mcp.service
```

查看状态：

```bash
systemctl --user status hpc-agent-mcp.service
```

修改 `.env` 或代码后重启：

```bash
systemctl --user restart hpc-agent-mcp.service
```

查看日志：

```bash
journalctl --user -u hpc-agent-mcp.service -f
tail -f ~/.local/share/hpc-agent/logs/mcp-http.log
tail -f ~/.local/share/hpc-agent/mcp_audit.jsonl
```

如果在 Linux 服务器上运行，并希望用户退出登录后服务仍然保持，可以开启 linger：

```bash
loginctl enable-linger "$USER"
```

## 浏览器客户端 URL

ChatGPT Web 这类浏览器客户端通常填写：

```text
https://hpc-agent.example.com/mcp
```

ChatGPT 应用描述可以参考：

```text
docs/mcp_docs/MCP_CHATGPT_APP_METADATA.md
```

其他 MCP 客户端接入建议见：

```text
docs/mcp_docs/MCP_CLIENTS.md
```

## 安全默认值

除非进行受控写入测试，否则保持关闭：

```bash
HPC_AGENT_MCP_ENABLE_WRITE=0
HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=0
```

即使开启环境变量，写入类工具仍必须传入 `confirm=true`。
