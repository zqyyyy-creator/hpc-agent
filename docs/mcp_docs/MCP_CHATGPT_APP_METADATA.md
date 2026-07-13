# ChatGPT 应用元信息模板

这是面向 ChatGPT Web 的客户端专项示例。HPC Agent MCP 接口不是 ChatGPT 专用协议；其他 MCP 客户端可以使用自己的元信息、提示词或连接配置接入同一个服务。

在 ChatGPT 开发者模式中创建或编辑 MCP 应用时，可以使用下面的名称和描述。

## 名称

```text
HPC Agent
```

## 描述

```text
HPC Agent 是一个面向超算、Slurm 和 VASP 工作流的助手。当用户询问 HPC 配置、集群/分区知识、Slurm sbatch 脚本、作业提交预览、提交已审核脚本、查看最近或指定 Slurm 作业、读取 stdout/stderr 日志、诊断作业失败、准备 VASP 作业、生成 VASP 输入文件、同步 VASP 输出、分析本地 VASP 结果或清理远端作业文件时，可以使用它。

普通自然语言对话优先调用 hpc_agent_chat。它会复用 HPC Agent TUI 的意图路由层，能保留“提交刚才那个”“查看上一个作业”等上下文，并返回简短助手回复和结构化数据。

不要优先调用低层工具，除非用户明确要求某个具体操作，或 hpc_agent_chat 返回了明确下一步。hpc_generate_sbatch 仅用于明确的 Slurm 脚本预览生成。hpc_query_job 仅在已知具体 job_id 时使用。vasp_analyze_local_result 仅用于本地 VASP 输出目录，不用于实时 Slurm job id。

安全规则：默认先生成预览，再执行。除非用户明确确认，否则不要提交、同步或删除。真实提交和 VASP 同步需要 confirm=true，并且服务端设置 HPC_AGENT_MCP_ENABLE_WRITE=1。远端清理需要 confirm=true，并且服务端设置 HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1。如果 hpc_agent_chat 返回 pending_submission，应先让用户确认，再用 confirm=true 调用 hpc_agent_chat。
```

## 首次测试提示词

```text
检查当前 HPC 配置
```

```text
生成 Slurm 脚本预览：command: hostname nodes: 1 time: 00:05:00 partition: amd_test
```

```text
帮我提交一个普通 Slurm 作业运行 hostname，1 核，5 分钟
```

```text
提交刚才那个
```

最后一个提示词不应直接执行，除非用户明确确认，并且 MCP 调用带有 `confirm=true`，服务端同时设置了 `HPC_AGENT_MCP_ENABLE_WRITE=1`。
