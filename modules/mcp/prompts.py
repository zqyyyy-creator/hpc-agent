from __future__ import annotations


def submit_slurm_job() -> str:
    return """你正在通过 hpc-agent 帮用户安全提交 Slurm 作业。

推荐流程：
1. 如果缺少信息，先询问运行命令、CPU/GPU、运行时间、分区以及输入/输出文件。
2. 调用 hpc_generate_sbatch 生成脚本预览。
3. 展示脚本，并明确说明当前还没有提交作业。
4. 只有在用户明确确认且服务端允许写入执行时，才调用 hpc_submit_prepared_job。
"""


def diagnose_slurm_error() -> str:
    return """你正在通过 hpc-agent 诊断 Slurm/HPC 作业。

推荐流程：
1. 如果没有 Job ID，先询问用户。
2. 调用 hpc_query_job，query_type="status"。
3. 调用 hpc_query_job，query_type="error"；必要时再调用 query_type="output"。
4. 总结可能原因，引用观察到的日志片段，并给出安全的下一步建议。
"""


def prepare_vasp_job() -> str:
    return """你正在通过 hpc-agent 准备 VASP 作业。

推荐流程：
1. 确认本地 VASP 输入目录；如果缺失，先让用户指定。
2. 如果目录里有 POTCAR，但缺少 INCAR/KPOINTS/POSCAR，可以调用 vasp_generate_inputs。
3. 调用 hpc_prepare_vasp_job 生成 Slurm 脚本预览。
4. 明确说明没有上传文件，也没有提交作业。
"""


def analyze_vasp_result() -> str:
    return """你正在通过 hpc-agent 分析本地 VASP 结果。

推荐流程：
1. 如果缺少本地 VASP 输出目录，先询问用户。
2. 调用 vasp_analyze_local_result 并传入该目录。
3. 总结收敛情况、发现的问题、生成的上下文路径、图表信息和下一步建议。
"""


def cleanup_remote_job() -> str:
    return """你正在通过 hpc-agent 准备远端清理。

推荐流程：
1. 如果缺少 Job ID、VASP selector 或清理范围，先询问用户。
2. 只调用 hpc_prepare_cleanup 预览清理目标。
3. 清楚展示每一个目标路径。
4. 只有在用户明确确认且服务端允许危险操作时，才调用 hpc_execute_cleanup。
"""


def natural_language_agent() -> str:
    return """请通过 HPC Agent 的主自然语言 MCP 入口处理普通请求。

推荐流程：
1. 普通用户请求优先使用 hpc_agent_chat，尤其是“上一个作业”“提交刚才的预览”等依赖上下文的表达。
2. 面向用户展示时优先读取 reply/plain_text 字段，结构化处理时读取 data 字段。
3. 如果 hpc_agent_chat 返回 pending_submission，先展示简短预览摘要并要求用户明确确认。
4. 用户明确确认后，再用 confirm=true 调用 hpc_agent_chat，或使用专用受保护提交工具。
"""


def submit_safe_workflow() -> str:
    return """通过 MCP 安全提交 HPC 作业。

推荐流程：
1. 先用 hpc_agent_chat 或 hpc_generate_sbatch_structured 生成预览。
2. 不要自动提交刚生成的脚本。
3. 让用户确认脚本、分区、运行时间和命令。
4. 只有在 confirm=true 且服务端开启 HPC_AGENT_MCP_ENABLE_WRITE=1 时才提交。
5. 提交后根据 job id 查询状态，再读取输出/错误日志。
"""


def vasp_full_workflow() -> str:
    return """通过 HPC Agent MCP 执行 VASP 工作流。

推荐流程：
1. 确认或创建本地 VASP 输入目录。
2. 在合适情况下，用 vasp_generate_inputs 生成缺失的 INCAR/KPOINTS/POSCAR。
3. 用 hpc_prepare_vasp_job 或 hpc_agent_chat 生成 VASP Slurm 预览。
4. 只有在用户明确确认且写入开关开启后才提交。
5. 作业完成后，用 vasp_sync_output 同步输出，再用 vasp_analyze_local_result 分析本地结果。
"""


def debug_connection() -> str:
    return """排查 HPC Agent MCP 连接问题。

推荐流程：
1. 检查本地 HTTP 健康接口：GET /health。
2. 如果使用 tunnel，检查 https://HOST/health。
3. 确认 MCP URL 以 /mcp 结尾，而不是 /health 或 /。
4. 如果日志出现 Invalid Host header，把 HPC_AGENT_MCP_ALLOWED_HOST 设置为 tunnel/固定域名 host 并重启。
5. MCP 连接成功后调用 hpc_check_config 检查 HPC 配置。
"""
