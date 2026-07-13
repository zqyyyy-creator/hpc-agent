# 通用 MCP 客户端接入说明

HPC Agent 提供的是标准 MCP 服务，不是 ChatGPT 专用接口。只要客户端支持 MCP 的 STDIO 或 Streamable HTTP 传输，就可以接入同一个 `hpc-agent-mcp` 服务。

## 推荐调用方式

普通自然语言对话优先使用：

```text
hpc_agent_chat
```

这个工具会复用 TUI 的意图路由和上下文状态，适合处理“提交刚才那个”“查看上一个作业”“分析这个 VASP 结果”这类依赖上下文的请求。

当客户端已经拿到了明确参数时，优先使用结构化工具，避免再让模型解析自然语言：

```text
hpc_generate_sbatch_structured
hpc_prepare_vasp_job_structured
vasp_generate_inputs_structured
vasp_analyze_local_result_structured
vasp_sync_output_structured
hpc_query_job_structured
hpc_prepare_cleanup_structured
```

低层自然语言工具仍然保留，主要用于兼容旧客户端或调试具体工具。

## 传输方式

桌面客户端如果能直接启动本地命令，推荐 STDIO：

```bash
hpc-agent-mcp
```

浏览器客户端、远程客户端或需要 URL 的客户端，使用 Streamable HTTP：

```bash
hpc-agent-mcp --transport streamable-http --host 127.0.0.1 --port 8000 --path /mcp
```

如果通过 Cloudflare Tunnel、ngrok 或反向代理访问，需要放行公网 Host：

```bash
hpc-agent-mcp \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8000 \
  --path /mcp \
  --allowed-host YOUR-PUBLIC-HOST
```

## 客户端可读资源

支持读取 MCP resources 的客户端建议先读取：

```text
hpc-agent://capabilities
hpc-agent://schema/tools
hpc-agent://security/policy
hpc-agent://examples
```

其中 `schema/tools` 描述统一返回格式和结构化工具参数，`security/policy` 描述确认机制、安全开关和审计行为。

## 安全规则

预览类工具只生成脚本或目标列表，不会执行提交或删除：

```text
hpc_generate_sbatch_structured
hpc_prepare_vasp_job_structured
hpc_prepare_cleanup_structured
```

执行类工具必须由用户明确确认：

```text
hpc_submit_prepared_job
vasp_sync_output_structured
hpc_execute_cleanup
```

真实提交和 VASP 输出同步需要：

```text
confirm=true
HPC_AGENT_MCP_ENABLE_WRITE=1
```

远端清理需要：

```text
confirm=true
HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1
```

## 冒烟测试

连接成功后，先调用只读或预览工具：

```text
hpc_check_config
hpc_get_cluster_info(query="amd_test partition")
hpc_generate_sbatch_structured(command="hostname", nodes=1, time_limit="00:05:00", partition="amd_test")
```

再测试自然语言入口：

```text
hpc_agent_chat(message="生成 Slurm 脚本预览：command: hostname nodes: 1 time: 00:05:00 partition: amd_test")
```

VASP 本地分析建议传明确路径：

```text
vasp_analyze_local_result_structured(local_job_dir="/home/qyz/vasp-jobs-output/si_static_test")
```

## 客户端专项文档

ChatGPT Web 是其中一个客户端示例：

```text
docs/mcp_docs/MCP_CHATGPT_WEB.md
docs/mcp_docs/MCP_CHATGPT_APP_METADATA.md
```
