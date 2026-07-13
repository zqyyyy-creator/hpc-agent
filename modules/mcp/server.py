from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from modules.mcp import prompts, resources, tools


def hpc_check_install() -> dict:
    """只读安装体检。用户询问 hpc-agent 是否安装正确、当前版本、资源文件、文档、skills 或命令入口是否完整时使用。"""
    return tools.check_install()


def hpc_check_config() -> dict:
    """只读 HPC 配置检查。用户询问 .env、SSH、API key、本地目录、远端目录、VASP 命令或 Slurm 分区可达性时使用。"""
    return tools.check_config()


def hpc_agent_user_guide() -> str:
    """读取内置 hpc-agent 用户手册。"""
    return resources.user_guide()


def hpc_agent_cluster_info() -> str:
    """读取内置集群和 HPC 知识文档。"""
    return resources.cluster_info()


def hpc_agent_skills() -> str:
    """读取已加载的 hpc-agent skills 和被跳过的自定义 skills。"""
    return resources.skills_json()


def hpc_agent_config_status() -> str:
    """读取脱敏后的 hpc-agent 配置状态。"""
    return resources.config_status_json()


def hpc_agent_recent_jobs() -> str:
    """读取最近本地登记的 Slurm/VASP 作业。"""
    return resources.recent_jobs_json()


def hpc_agent_capabilities() -> str:
    """读取 MCP 能力、风险级别、安全开关和推荐客户端行为。"""
    return resources.capabilities_json()


def hpc_agent_tool_schema() -> str:
    """读取稳定返回结构和结构化工具输入 schema。"""
    return resources.tool_schema_json()


def hpc_agent_deployment_status() -> str:
    """读取部署相关状态，例如健康检查接口、审计路径和安全开关环境变量名。"""
    return resources.deployment_status_json()


def hpc_agent_security_policy() -> str:
    """读取 MCP 安全策略、确认机制、危险工具规则和审计行为。"""
    return resources.security_policy_json()


def hpc_agent_examples() -> str:
    """读取自然语言、结构化和受保护工作流的 MCP 调用示例。"""
    return resources.examples_json()


def submit_slurm_job_prompt() -> str:
    """指导安全的 Slurm 提交流程。"""
    return prompts.submit_slurm_job()


def diagnose_slurm_error_prompt() -> str:
    """指导 Slurm 作业错误诊断。"""
    return prompts.diagnose_slurm_error()


def prepare_vasp_job_prompt() -> str:
    """指导 VASP 输入和作业预览准备。"""
    return prompts.prepare_vasp_job()


def analyze_vasp_result_prompt() -> str:
    """指导本地 VASP 结果分析。"""
    return prompts.analyze_vasp_result()


def cleanup_remote_job_prompt() -> str:
    """指导安全的远端清理预览和执行。"""
    return prompts.cleanup_remote_job()


def natural_language_agent_prompt() -> str:
    """指导通用客户端把 hpc_agent_chat 作为主自然语言入口。"""
    return prompts.natural_language_agent()


def submit_safe_workflow_prompt() -> str:
    """指导任何 MCP 客户端遵循先预览、确认后提交。"""
    return prompts.submit_safe_workflow()


def vasp_full_workflow_prompt() -> str:
    """指导 VASP 输入、提交、同步和本地分析完整流程。"""
    return prompts.vasp_full_workflow()


def debug_connection_prompt() -> str:
    """指导 MCP HTTP、tunnel 和 Host header 连接排查。"""
    return prompts.debug_connection()


def hpc_get_cluster_info(query: str, top_k: int = 5) -> dict:
    """只读知识查询。用于分区、存储路径、Slurm 用法、GPU 队列、环境模块、VASP 注意事项或集群规则；不要用于实时作业状态。"""
    return tools.get_cluster_info(query, top_k=top_k)


def hpc_list_skills(include_skipped: bool = True) -> dict:
    """只读 skill 清单。用户询问有哪些内置/外部 skills、哪些已加载/跳过、skills 如何映射到 intent 时使用。"""
    return tools.list_skills(include_skipped=include_skipped)


def hpc_agent_chat(message: str, confirm: bool = False) -> dict:
    """HPC Agent 的主自然语言入口。普通请求优先使用它，包括 Slurm 脚本、作业提交预览、提交上一个预览、查看最近作业、作业日志、VASP 工作流、配置检查、诊断和集群问答。它复用 TUI 的意图路由并保留上下文，返回简短回复和结构化数据，不会绕过写入保护。用户明确确认后的真实提交/同步/清理需传 confirm=true，或使用专用受保护执行工具。"""
    return tools.agent_chat(message, confirm=confirm)


def hpc_generate_sbatch(request: str) -> dict:
    """根据具体请求生成 Slurm sbatch 脚本预览。适用于用户已经提供 command/time/nodes/partition 的低层脚本生成；不会提交。普通对话优先使用 hpc_agent_chat。"""
    return tools.generate_sbatch(request)


def hpc_generate_sbatch_structured(
    command: str,
    nodes: int = 1,
    time_limit: str = "00:10:00",
    partition: str | None = None,
    cpus_per_task: int = 1,
    job_name: str = "hpc_agent_job",
    memory: str | None = None,
    gpu_count: int | None = None,
) -> dict:
    """结构化 Slurm sbatch 预览生成器。客户端已知 command、nodes、time_limit、partition、cpus_per_task、job_name、memory 或 gpu_count，且希望避免自然语言解析时使用。只返回脚本预览，永不提交。"""
    return tools.generate_sbatch_structured(
        command=command,
        nodes=nodes,
        time_limit=time_limit,
        partition=partition,
        cpus_per_task=cpus_per_task,
        job_name=job_name,
        memory=memory,
        gpu_count=gpu_count,
    )


def hpc_submit_prepared_job(
    script: str,
    submission_kind: str = "slurm",
    source_text: str = "",
    run_name: str | None = None,
    confirm: bool = False,
) -> dict:
    """受保护写入工具，用于提交已经审核过的 Slurm 或 VASP 脚本。仅在已有脚本预览且用户明确确认后使用。需要 confirm=true 和 HPC_AGENT_MCP_ENABLE_WRITE=1，否则拒绝执行。自然语言“提交刚才的预览”优先用 hpc_agent_chat 并传 confirm=true。"""
    if submission_kind not in {"slurm", "vasp"}:
        return {
            "ok": False,
            "risk": "write_execute",
            "message": "submission_kind 必须是 slurm 或 vasp。",
            "submission_kind": submission_kind,
        }
    return tools.submit_prepared_job(
        script,
        submission_kind,  # type: ignore[arg-type]
        source_text=source_text,
        run_name=run_name,
        confirm=confirm,
    )


def hpc_prepare_vasp_job(request: str) -> dict:
    """根据本地 VASP 输入目录或自然语言 VASP 请求生成 VASP Slurm 作业预览。不会提交、上传或同步文件。对话式 VASP 工作流优先使用 hpc_agent_chat。"""
    return tools.prepare_vasp_job(request)


def hpc_prepare_vasp_job_structured(
    local_input_dir: str,
    partition: str | None = None,
    nodes: int = 1,
    time_limit: str = "01:00:00",
    job_name: str | None = None,
    vasp_command: str | None = None,
    setup_command: str | None = None,
) -> dict:
    """结构化 VASP Slurm 预览生成器。客户端已知本地 VASP 输入目录和资源设置时使用。只返回预览，永不提交、上传或同步文件。"""
    return tools.prepare_vasp_job_structured(
        local_input_dir=local_input_dir,
        partition=partition,
        nodes=nodes,
        time_limit=time_limit,
        job_name=job_name,
        vasp_command=vasp_command,
        setup_command=setup_command,
    )


def vasp_generate_inputs(request: str, jobs_dir: str | None = None) -> dict:
    """本地写入型 VASP 输入生成器。用户希望根据 POTCAR 和材料/计算描述生成 INCAR、KPOINTS、POSCAR 或完整本地输入集时使用。只写本地文件，不提交。"""
    return tools.generate_vasp_inputs(request, jobs_dir=jobs_dir)


def vasp_generate_inputs_structured(
    job_name: str,
    element: str | None = None,
    formula: str | None = None,
    calculation_type: str = "static",
    encut: int | None = None,
    kpoints: list[int] | None = None,
    jobs_dir: str | None = None,
    description: str = "",
    overwrite: bool = False,
) -> dict:
    """结构化本地 VASP 输入生成器。客户端已有明确作业、材料和计算参数，并希望避免自然语言解析时使用。只写本地输入文件，永不提交。"""
    if kpoints is not None and (len(kpoints) != 3 or not all(isinstance(value, int) for value in kpoints)):
        return {
            "ok": False,
            "risk": "write_local",
            "message": "kpoints 必须是恰好三个整数的列表，例如 [2, 2, 2]。",
            "kpoints": kpoints,
        }
    return tools.generate_vasp_inputs_structured(
        job_name=job_name,
        element=element,
        formula=formula,
        calculation_type=calculation_type,
        encut=encut,
        kpoints=kpoints,
        jobs_dir=jobs_dir,
        description=description,
        overwrite=overwrite,
    )


def vasp_analyze_local_result(local_job_dir: str) -> dict:
    """本地写入型 VASP 结果分析工具。用户提供本地 VASP 输出/作业目录、raw_output 目录或包含 OUTCAR/OSZICAR/vasprun.xml 的目录时使用。会在 analysis/ 下生成报告上下文和图表元数据。它分析本地文件，不查询实时 Slurm job id。"""
    return tools.analyze_vasp_local_result(local_job_dir)


def vasp_analyze_local_result_structured(local_job_dir: str) -> dict:
    """结构化本地 VASP 结果分析工具。客户端已有明确本地作业/output/raw_output 目录时使用。它分析目录内容并在本地写入分析元数据，不查询 Slurm。"""
    return tools.analyze_vasp_local_result_structured(local_job_dir)


def vasp_sync_output(job_id: str, confirm: bool = False) -> dict:
    """受保护写入工具，把指定 Slurm job id 的远端 VASP 输出同步到本地输出目录。仅在用户明确要求同步结果后使用。需要 confirm=true 和 HPC_AGENT_MCP_ENABLE_WRITE=1，否则拒绝执行。"""
    return tools.sync_vasp_output(job_id, confirm=confirm)


def vasp_sync_output_structured(job_id: str, confirm: bool = False) -> dict:
    """结构化受保护 VASP 同步工具。客户端已有明确 Slurm job id，且用户要求把远端 VASP 输出复制回本地时使用。需要 confirm=true 和 HPC_AGENT_MCP_ENABLE_WRITE=1。"""
    return tools.sync_vasp_output_structured(job_id, confirm=confirm)


def hpc_query_job(job_id: str, query_type: str = "status") -> dict:
    """只读实时 Slurm 作业查询。用户提供 job id 并询问状态、stdout 输出、stderr 错误日志或详情时使用。query_type 必须是 status、output、error 或 detail。对于“查看上一个作业”这类上下文请求，优先用 hpc_agent_chat 解析 job id。"""
    if query_type not in {"status", "output", "error", "detail"}:
        return {
            "ok": False,
            "risk": "read_only",
            "message": "query_type 必须是 status、output、error 或 detail。",
            "job_id": job_id,
            "query_type": query_type,
        }
    return tools.query_job(job_id, query_type)  # type: ignore[arg-type]


def hpc_query_job_structured(job_id: str, query_type: str = "status") -> dict:
    """结构化只读 Slurm 作业查询。客户端已有明确 job id 和查询类型时使用。对于“最近作业”这类依赖上下文的表达，请改用 hpc_agent_chat。"""
    if query_type not in {"status", "output", "error", "detail"}:
        return {
            "ok": False,
            "risk": "read_only",
            "message": "query_type 必须是 status、output、error 或 detail。",
            "job_id": job_id,
            "query_type": query_type,
        }
    return tools.query_job_structured(job_id, query_type)  # type: ignore[arg-type]


def hpc_prepare_cleanup(request: str, cleanup_type: str = "job") -> dict:
    """危险操作预览工具。仅用于列出某个 Slurm/VASP 作业或全部作业将被清理的远端文件/目录。它不会删除任何内容。cleanup_type 可为 job、all_jobs、vasp_job 或 all_vasp_jobs。"""
    if cleanup_type not in {"job", "all_jobs", "vasp_job", "all_vasp_jobs"}:
        return {
            "ok": False,
            "risk": "destructive_preview",
            "message": "cleanup_type 必须是 job、all_jobs、vasp_job 或 all_vasp_jobs。",
            "cleanup_type": cleanup_type,
        }
    return tools.prepare_cleanup(request, cleanup_type)  # type: ignore[arg-type]


def hpc_prepare_cleanup_structured(
    cleanup_type: str = "job",
    job_id: str | None = None,
    selector: str | None = None,
    scope: str = "all",
) -> dict:
    """结构化危险操作预览工具。用于预览指定 Slurm job id、VASP selector 或全部作业清理会删除哪些内容。它永不删除文件；真正删除需要 hpc_execute_cleanup、用户明确确认和危险操作环境开关。"""
    if cleanup_type not in {"job", "all_jobs", "vasp_job", "all_vasp_jobs"}:
        return {
            "ok": False,
            "risk": "destructive_preview",
            "message": "cleanup_type 必须是 job、all_jobs、vasp_job 或 all_vasp_jobs。",
            "cleanup_type": cleanup_type,
        }
    if cleanup_type in {"job", "vasp_job"} and not (job_id or selector):
        return {
            "ok": False,
            "risk": "destructive_preview",
            "message": "job 和 vasp_job 清理预览必须提供 job_id 或 selector。",
            "cleanup_type": cleanup_type,
        }
    if scope not in {"all", "input", "output", "input_and_output"}:
        return {
            "ok": False,
            "risk": "destructive_preview",
            "message": "scope 必须是 all、input、output 或 input_and_output。",
            "scope": scope,
        }
    return tools.prepare_cleanup_structured(
        cleanup_type=cleanup_type,  # type: ignore[arg-type]
        job_id=job_id,
        selector=selector,
        scope=scope,
    )


def hpc_execute_cleanup(
    targets: list[dict[str, Any]],
    cleanup_kind: str = "",
    confirm: bool = False,
) -> dict:
    """受保护危险工具，用于删除之前已经预览过的远端清理目标。只能在 hpc_prepare_cleanup 之后且用户明确确认时使用。需要 confirm=true 和 HPC_AGENT_MCP_ENABLE_DESTRUCTIVE=1，否则拒绝执行。"""
    return tools.execute_cleanup(targets, cleanup_kind=cleanup_kind, confirm=confirm)


def mcp_health(streamable_http_path: str = "/mcp") -> JSONResponse:
    """部署健康检查 HTTP 接口。它不是 MCP 工具。"""
    return JSONResponse({
        "ok": True,
        "service": "hpc-agent-mcp",
        "transport": "streamable-http",
        "mcp_path": streamable_http_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def create_mcp_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    streamable_http_path: str = "/mcp",
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
) -> FastMCP:
    transport_security = None
    if allowed_hosts or allowed_origins:
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1:*",
                "localhost:*",
                "[::1]:*",
                *(allowed_hosts or []),
            ],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
                *(allowed_origins or []),
            ],
        )

    server = FastMCP(
        "hpc-agent",
        host=host,
        port=port,
        streamable_http_path=streamable_http_path,
        transport_security=transport_security,
    )
    register_capabilities(server)
    server.custom_route("/health", methods=["GET"], include_in_schema=False)(
        lambda request: mcp_health(streamable_http_path)
    )
    return server


def register_capabilities(server: FastMCP) -> FastMCP:
    server.tool()(hpc_check_install)
    server.tool()(hpc_check_config)
    server.tool()(hpc_get_cluster_info)
    server.tool()(hpc_list_skills)
    server.tool()(hpc_agent_chat)
    server.tool()(hpc_generate_sbatch)
    server.tool()(hpc_generate_sbatch_structured)
    server.tool()(hpc_submit_prepared_job)
    server.tool()(hpc_prepare_vasp_job)
    server.tool()(hpc_prepare_vasp_job_structured)
    server.tool()(vasp_generate_inputs)
    server.tool()(vasp_generate_inputs_structured)
    server.tool()(vasp_analyze_local_result)
    server.tool()(vasp_analyze_local_result_structured)
    server.tool()(vasp_sync_output)
    server.tool()(vasp_sync_output_structured)
    server.tool()(hpc_query_job)
    server.tool()(hpc_query_job_structured)
    server.tool()(hpc_prepare_cleanup)
    server.tool()(hpc_prepare_cleanup_structured)
    server.tool()(hpc_execute_cleanup)

    server.resource("hpc-agent://docs/user-guide", mime_type="text/markdown")(hpc_agent_user_guide)
    server.resource("hpc-agent://cluster/info", mime_type="text/plain")(hpc_agent_cluster_info)
    server.resource("hpc-agent://skills", mime_type="application/json")(hpc_agent_skills)
    server.resource("hpc-agent://config/status", mime_type="application/json")(hpc_agent_config_status)
    server.resource("hpc-agent://jobs/recent", mime_type="application/json")(hpc_agent_recent_jobs)
    server.resource("hpc-agent://capabilities", mime_type="application/json")(hpc_agent_capabilities)
    server.resource("hpc-agent://schema/tools", mime_type="application/json")(hpc_agent_tool_schema)
    server.resource("hpc-agent://deployment/status", mime_type="application/json")(hpc_agent_deployment_status)
    server.resource("hpc-agent://security/policy", mime_type="application/json")(hpc_agent_security_policy)
    server.resource("hpc-agent://examples", mime_type="application/json")(hpc_agent_examples)

    server.prompt(name="submit-slurm-job")(submit_slurm_job_prompt)
    server.prompt(name="diagnose-slurm-error")(diagnose_slurm_error_prompt)
    server.prompt(name="prepare-vasp-job")(prepare_vasp_job_prompt)
    server.prompt(name="analyze-vasp-result")(analyze_vasp_result_prompt)
    server.prompt(name="cleanup-remote-job")(cleanup_remote_job_prompt)
    server.prompt(name="hpc-agent-natural-language")(natural_language_agent_prompt)
    server.prompt(name="hpc-agent-submit-safe-workflow")(submit_safe_workflow_prompt)
    server.prompt(name="hpc-agent-vasp-full-workflow")(vasp_full_workflow_prompt)
    server.prompt(name="hpc-agent-debug-connection")(debug_connection_prompt)

    return server


mcp = create_mcp_server()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="运行 hpc-agent MCP 服务。")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="MCP 传输方式。",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="streamable-http 监听 Host。",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="streamable-http 监听端口。",
    )
    parser.add_argument(
        "--path",
        default="/mcp",
        help="streamable-http MCP 路径。",
    )
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=[],
        help="额外允许的 streamable-http Host header，例如 tunnel 域名。",
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help="额外允许的 streamable-http Origin。",
    )
    args = parser.parse_args(argv)

    active_server = (
        create_mcp_server(
            host=args.host,
            port=args.port,
            streamable_http_path=args.path,
            allowed_hosts=args.allowed_host,
            allowed_origins=args.allowed_origin,
        )
        if args.transport == "streamable-http"
        else mcp
    )
    active_server.run(transport=args.transport)


if __name__ == "__main__":
    main()
