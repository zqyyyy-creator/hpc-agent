# HPC Agent Docs

这里是 HPC Agent 的文档入口。第一次使用建议先看用户手册；做发布、演示或真实集群验收时再看 Live Test Checklist。

## 文档导航

| 文档 | 用途 |
| --- | --- |
| [USER_GUIDE.md](USER_GUIDE.md) | 配置、启动、日常使用、普通 Slurm 作业、VASP 作业、错误诊断、快捷命令和 TUI 操作说明 |
| [mcp_docs/MCP.md](mcp_docs/MCP.md) | MCP 服务总说明，包含工具、资源、结构化参数、安全开关和冒烟测试 |
| [mcp_docs/MCP_CLIENTS.md](mcp_docs/MCP_CLIENTS.md) | 通用 MCP 客户端接入说明，适用于 ChatGPT、Claude Desktop、Cursor、Codex 等客户端 |
| [mcp_docs/MCP_CHATGPT_WEB.md](mcp_docs/MCP_CHATGPT_WEB.md) | ChatGPT Web 通过 HTTPS tunnel 接入 MCP 的具体步骤 |
| [mcp_docs/MCP_DEPLOYMENT.md](mcp_docs/MCP_DEPLOYMENT.md) | MCP HTTP 服务、健康检查、systemd、日志和审计部署说明 |
| [mcp_docs/EXTERNAL_MCP_INJECTION.md](mcp_docs/EXTERNAL_MCP_INJECTION.md) | HPC Agent 作为 MCP Client 注入外部 MCP tools |
| [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md) | 外部只读 Skills 接入方式，包含 `SKILL.md + handler.py` 模板和调试命令 |
| [LIVE_TEST_CHECKLIST.md](LIVE_TEST_CHECKLIST.md) | 真实超算环境验收清单，记录 Slurm / VASP 提交、监控、同步、分析结果 |
| [VASP_TEST_TEMPLATES.md](VASP_TEST_TEMPLATES.md) | 推荐 VASP 测试体系、输入文件模板、资源建议和通过标准 |
| [../data/errors/README.md](../data/errors/README.md) | 错误知识库维护说明，区分真实案例库和通用错误库，说明半自动入库和脱敏要求 |

## 推荐阅读顺序

1. 新用户先读 [USER_GUIDE.md](USER_GUIDE.md)。
2. 配置好 `.env` 后，按 [LIVE_TEST_CHECKLIST.md](LIVE_TEST_CHECKLIST.md) 做真实环境验收。
3. 需要准备 VASP smoke test 时，参考 [VASP_TEST_TEMPLATES.md](VASP_TEST_TEMPLATES.md)。
4. 需要接入本地自定义 Skills 时，参考 [EXTERNAL_SKILLS.md](EXTERNAL_SKILLS.md)。
5. 需要接入外部 AI/MCP 客户端时，先看 [mcp_docs/MCP.md](mcp_docs/MCP.md)，再按客户端类型看对应专项文档。
6. 需要让 HPC Agent 调用外部 MCP tools 时，看 [mcp_docs/EXTERNAL_MCP_INJECTION.md](mcp_docs/EXTERNAL_MCP_INJECTION.md)。

## 常用入口

- 启动 TUI：`.venv/bin/python app.py`
- 安装版启动 TUI：`hpc-agent`
- 启动 MCP STDIO：`hpc-agent-mcp`
- 启动 MCP HTTP：`hpc-agent-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp`
- 外部 MCP 注入管理：`hpc-agent-mcp-client doctor` / `hpc-agent-mcp-client list-tools`
- MCP 健康检查：`curl http://127.0.0.1:8000/health`
- 本地全量检查：`hpc-agent-check`
- 真实 HPC 检查：`hpc-agent-check --live-hpc`
- 配置检查：在 TUI 输入 `检查我的超算配置`
- TUI 快捷帮助：`/help`
- Job 快捷帮助：`/help job`
- VASP 快捷帮助：`/help vasp`
- Skill 列表与 dry-run：`/skill list`、`/skill test all`
- 清理/退出：`/clear`、`/clear all`、`/exit`

## 维护约定

- 根目录 [../README.md](../README.md) 保持项目概览、安装和核心能力说明。
- `docs/README.md` 只做文档索引和阅读路径，不重复长篇操作说明。
- 新增重要文档时，同步在本页登记。
