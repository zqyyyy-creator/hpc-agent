import logging
import jieba

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.markdown import Markdown
from rich import box

from modules.knowledge_base import load_documents, retrieve, ask_llm
from modules.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.error_diagnoser import ErrorDiagnoser
from modules.job_submitter import (
    create_vasp_inputs_from_text,
    extract_vasp_job_selector,
    generate_vasp_template_inputs,
    import_vasp_inputs_from_text,
    write_vasp_input_files,
    register_existing_vasp_job_from_text,
    prepare_submit_script,
    prepare_vasp_submit_script,
    submit_prepared_script,
    submit_prepared_vasp_script,
)
from modules.vasp_assistant import generate_vasp_sbatch_script
from modules.job_query import (
    execute_cleanup_remote_jobs,
    extract_job_id,
    prepare_cleanup_all_remote_jobs,
    prepare_cleanup_remote_job,
    query_remote_agent_jobs,
    query_job_error,
    query_job_output,
    query_job_status,
)
from modules.router import detect_intent


jieba.setLogLevel(logging.ERROR)

console = Console()


def show_welcome():
    console.print(
        Panel.fit(
            "[bold cyan]HPC Agent 已启动[/bold cyan]\n\n"
            "[green]1.[/green] Slurm 知识库问答\n"
            "[green]2.[/green] Slurm sbatch 脚本生成\n"
            "[green]3.[/green] Slurm 参数建议\n"
            "[green]4.[/green] 错误日志诊断\n"
            "[green]5.[/green] 作业 Pending 排查\n\n"
            "[yellow]输入 quit 退出，按 Ctrl+C 中断当前操作[/yellow]",
            title="HPC Agent",
            border_style="cyan",
        )
    )


def show_intent(intent: str):
    table = Table(title="当前任务类型", box=box.ROUNDED)
    table.add_column("Intent", style="cyan")
    table.add_column("说明", style="green")

    mapping = {
        "rag_qa": "Slurm 知识库问答",
        "generate_sbatch": "生成 sbatch 脚本",
        "suggest_params": "Slurm 参数建议",
        "diagnose_error": "错误日志诊断",
        "troubleshoot_job": "作业 Pending / 不运行排查",
        "submit_job": "提交作业到超算",
        "generate_vasp_job": "生成 VASP 作业脚本",
        "submit_vasp_job": "提交 VASP 作业到超算",
        "create_vasp_inputs": "生成 VASP 输入文件",
        "import_vasp_inputs": "导入 VASP 输入文件",
        "assist_vasp_inputs": "Agent 辅助生成 VASP 输入模板",
        "register_vasp_job": "登记已有 VASP 作业",
        "job_status": "查询作业状态",
        "job_output": "读取作业输出",
        "job_error": "读取作业错误日志",
        "list_remote_jobs": "列出远端 Agent 作业编号",
        "cleanup_remote_job": "按 Job ID 清理远端普通作业文件",
        "cleanup_all_remote_jobs": "清理全部远端普通作业文件",
    }

    table.add_row(intent, mapping.get(intent, "未知任务"))
    console.print(table)


def handle_rag_qa(question, documents, sources):
    with console.status("[bold green]正在检索知识库...[/bold green]"):
        retrieved_docs = retrieve(question, documents, sources)

    if not retrieved_docs:
        console.print("[red]没有找到相关资料。[/red]")
        return

    with console.status("[bold green]正在生成回答...[/bold green]"):
        answer = ask_llm(question, retrieved_docs)

    console.print(Panel(Markdown(answer), title="AI 回答", border_style="green"))


def handle_generate_sbatch(question):
    with console.status("[bold green]正在生成 sbatch 脚本...[/bold green]"):
        script = generate_sbatch_script(question)

    console.print(Panel(script, title="生成的 Slurm 脚本", border_style="cyan"))


def handle_suggest_params(question):
    with console.status("[bold green]正在生成参数建议...[/bold green]"):
        suggestion = suggest_slurm_parameters(question)

    console.print(Panel(Markdown(suggestion), title="参数建议", border_style="yellow"))


def handle_submit_job(question):
    with console.status("[bold green]正在生成待提交脚本...[/bold green]"):
        prepared = prepare_submit_script(question)

    if not prepared["ready"]:
        console.print(Panel(prepared["message"], title="需要补充信息", border_style="yellow"))
        return

    console.print(Panel(prepared["script"], title="待提交 Slurm 脚本", border_style="cyan"))

    if not Confirm.ask("确认提交到超算？"):
        console.print("[yellow]已取消提交。[/yellow]")
        return

    with console.status("[bold green]正在连接超算并提交作业...[/bold green]"):
        result = submit_prepared_script(prepared["script"])

    border_style = "green" if result["success"] else "red"
    console.print(Panel(result["answer"], title="提交结果", border_style=border_style))


def handle_generate_vasp_job(question):
    with console.status("[bold green]正在生成 VASP sbatch 脚本...[/bold green]"):
        script = generate_vasp_sbatch_script(question)

    console.print(Panel(script, title="生成的 VASP Slurm 脚本", border_style="cyan"))


def should_ask_vasp_input_source(question: str):
    if extract_vasp_job_selector(question):
        return False

    normalized = question.lower().replace(" ", "")
    return not any(keyword in normalized for keyword in ["最近", "latest", "existing", "已有", "现有"])


def prompt_vasp_input_source(question: str):
    console.print(
        Panel(
            (
                "请选择 VASP 输入文件来源：\n\n"
                "1. 使用已有本地 VASP 作业目录\n"
                "2. 从导入目录导入四个 VASP 文件\n"
                "3. 在对话中粘贴四个 VASP 输入文件\n"
                "4. 让 Agent 辅助生成 VASP 输入模板\n\n"
                "输入 1 / 2 / 3 / 4，或输入 cancel 取消。"
            ),
            title="VASP 输入来源",
            border_style="yellow",
        )
    )

    choice = Prompt.ask("请选择").strip().lower()

    if choice in {"cancel", "取消", "n", "no"}:
        console.print("[yellow]已取消 VASP 提交。[/yellow]")
        return None

    if choice == "1":
        return question

    if choice == "2":
        result = import_vasp_inputs_from_text(question)
        border_style = "green" if result["success"] else "yellow"
        console.print(Panel(result["message"], title="VASP 输入文件导入结果", border_style=border_style))

        if not result["success"]:
            return None

        return f"{question} 目录名 {result['local_input_dir'].name}"

    if choice == "3":
        console.print(Panel("请按提示依次粘贴四个 VASP 输入文件。每个文件粘贴完成后输入 END。", title="手动粘贴模式", border_style="cyan"))
        inputs = {}

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            console.print(f"\n[cyan]请粘贴 {name}，完成后输入 END：[/cyan]")
            lines = []

            while True:
                line = input()

                if line.strip() == "END":
                    break

                lines.append(line)

            inputs[name] = "\n".join(lines)

        result = write_vasp_input_files(inputs)
        border_style = "green" if result["success"] else "yellow"
        console.print(Panel(result["message"], title="VASP 输入文件生成结果", border_style=border_style))

        if not result["success"]:
            return None

        return f"{question} 目录名 {result['local_input_dir'].name}"

    if choice == "4":
        result = generate_vasp_template_inputs(question)
        border_style = "green" if result["success"] else "yellow"
        console.print(Panel(result["message"], title="VASP 输入模板生成结果", border_style=border_style))

        if result.get("missing_files"):
            console.print("[yellow]模板目录还不完整，暂不进入提交预览。请补齐缺失文件后再提交。[/yellow]")
            return None

        return f"{question} 目录名 {result['local_input_dir'].name}"

    console.print("[yellow]无效选择，已取消 VASP 提交。[/yellow]")
    return None


def handle_submit_vasp_job(question):
    selector_text = question

    if should_ask_vasp_input_source(question):
        selector_text = prompt_vasp_input_source(question)

        if selector_text is None:
            return

    with console.status("[bold green]正在生成待提交 VASP 脚本...[/bold green]"):
        prepared = prepare_vasp_submit_script(question)

    if not prepared["ready"]:
        console.print(Panel(prepared["message"], title="需要补充信息", border_style="yellow"))
        return

    console.print(
        Panel(
            (
                f"本地 VASP 作业目录: {prepared['local_jobs_dir']}\n"
                "提交时默认选择最近保存的完整 VASP 作业；也可以在请求里写具体子目录名。\n"
                f"远程 VASP 作业根目录: {prepared['remote_workdir']}"
            ),
            title="VASP 作业目录",
            border_style="yellow",
        )
    )
    console.print(Panel(prepared["script"], title="待提交 VASP Slurm 脚本", border_style="cyan"))

    if not Confirm.ask("确认提交 VASP 作业到超算？"):
        console.print("[yellow]已取消提交。[/yellow]")
        return

    with console.status("[bold green]正在连接超算并提交 VASP 作业...[/bold green]"):
        result = submit_prepared_vasp_script(prepared["script"], selector_text)

    border_style = "green" if result["success"] else "red"
    console.print(Panel(result["answer"], title="VASP 提交结果", border_style=border_style))


def handle_create_vasp_inputs(question):
    if "```" in question:
        result = create_vasp_inputs_from_text(question)
    else:
        console.print(Panel("请按提示依次粘贴四个 VASP 输入文件。每个文件粘贴完成后输入 END。", title="手动粘贴模式", border_style="cyan"))
        inputs = {}

        for name in ["INCAR", "POSCAR", "POTCAR", "KPOINTS"]:
            console.print(f"\n[cyan]请粘贴 {name}，完成后输入 END：[/cyan]")
            lines = []

            while True:
                line = input()

                if line.strip() == "END":
                    break

                lines.append(line)

            inputs[name] = "\n".join(lines)

        result = write_vasp_input_files(inputs)

    border_style = "green" if result["success"] else "yellow"
    console.print(Panel(result["message"], title="VASP 输入文件生成结果", border_style=border_style))


def handle_import_vasp_inputs(question):
    result = import_vasp_inputs_from_text(question)
    border_style = "green" if result["success"] else "yellow"
    console.print(Panel(result["message"], title="VASP 输入文件导入结果", border_style=border_style))


def handle_assist_vasp_inputs(question):
    result = generate_vasp_template_inputs(question)
    border_style = "green" if result["success"] else "yellow"
    console.print(Panel(result["message"], title="VASP 输入模板生成结果", border_style=border_style))


def handle_register_vasp_job(question):
    result = register_existing_vasp_job_from_text(question)
    border_style = "green" if result["success"] else "yellow"
    console.print(Panel(result["message"], title="VASP 作业登记结果", border_style=border_style))


def handle_job_query(question, query_func, title):
    job_id = extract_job_id(question)

    if not job_id:
        console.print(Panel("请提供 job_id，例如：查看 11814709 的状态。", title="缺少 Job ID", border_style="yellow"))
        return

    with console.status("[bold green]正在连接超算查询作业...[/bold green]"):
        answer = query_func(job_id)

    console.print(Panel(answer, title=title, border_style="green"))


def handle_list_remote_jobs():
    with console.status("[bold green]正在扫描远端 Agent 作业目录...[/bold green]"):
        answer = query_remote_agent_jobs()

    console.print(Panel(answer, title="远端 Agent 作业编号", border_style="green"))


def handle_cleanup_remote_job(question):
    job_id = extract_job_id(question)

    if not job_id:
        console.print(Panel("请提供要清理的 Job ID，例如：清理远端作业 11817627 的文件。", title="缺少 Job ID", border_style="yellow"))
        return

    with console.status("[bold green]正在扫描远端普通作业文件...[/bold green]"):
        prepared = prepare_cleanup_remote_job(job_id)

    border_style = "red" if prepared["ready"] else "yellow"
    console.print(Panel(prepared["message"], title="清理预览", border_style=border_style))

    if not prepared["ready"]:
        return

    if not Confirm.ask("确认清理这些远端普通作业文件？"):
        console.print("[yellow]已取消清理。[/yellow]")
        return

    with console.status("[bold green]正在清理远端普通作业文件...[/bold green]"):
        answer = execute_cleanup_remote_jobs(prepared["targets"])

    console.print(Panel(answer, title="清理结果", border_style="green"))


def handle_cleanup_all_remote_jobs():
    with console.status("[bold green]正在扫描远端普通作业根目录...[/bold green]"):
        prepared = prepare_cleanup_all_remote_jobs()

    border_style = "red" if prepared["ready"] else "yellow"
    console.print(Panel(prepared["message"], title="清理全部预览", border_style=border_style))

    if not prepared["ready"]:
        return

    confirmation = Prompt.ask("这是高风险操作。请输入“确认清理全部”继续")

    if confirmation.strip() != "确认清理全部":
        console.print("[yellow]已取消清理。[/yellow]")
        return

    with console.status("[bold green]正在清理全部远端普通作业文件...[/bold green]"):
        answer = execute_cleanup_remote_jobs(prepared["targets"])

    console.print(Panel(answer, title="清理结果", border_style="green"))


def handle_troubleshoot_job(question, documents, sources):
    with console.status("[bold green]正在分析作业状态问题...[/bold green]"):
        retrieved_docs = retrieve(question, documents, sources)
        answer = ask_llm(question, retrieved_docs)

    console.print(Panel(Markdown(answer), title="作业排查建议", border_style="yellow"))


def diagnose_and_show(log_text, diagnoser):
    results = diagnoser.diagnose(log_text)

    console.print()
    console.print(Panel(diagnoser.format_results(results), title="诊断结果", border_style="red"))

    if results:
        choice = Confirm.ask("是否要根据该错误自动修复 sbatch 脚本？")

        if choice:
            console.print("\n请粘贴 sbatch 脚本。粘贴完成后输入 END：")

            script_lines = []

            while True:
                line = input()

                if line.strip() == "END":
                    break

                script_lines.append(line)

            if script_lines:
                original_script = "\n".join(script_lines)
                fixed_script = diagnoser.fix_sbatch_script(original_script, results)

                console.print(
                    Panel(
                        fixed_script,
                        title="修复后的 sbatch 脚本",
                        border_style="green",
                    )
                )


def handle_diagnose_error(diagnoser, initial_log=None):
    if initial_log:
        diagnose_and_show(initial_log, diagnoser)

    console.print(
        Panel(
            "可以继续粘贴完整错误日志。\n输入 [bold]quit[/bold] 返回主菜单。",
            title="错误日志诊断模式",
            border_style="red",
        )
    )

    while True:
        try:
            log_text = Prompt.ask("\n[red]error-log>[/red]").strip()

            if log_text.lower() == "quit":
                console.print("[yellow]已退出错误诊断模式。[/yellow]")
                break

            if not log_text:
                continue

            diagnose_and_show(log_text, diagnoser)

        except KeyboardInterrupt:
            console.print("\n[yellow]已中断当前错误诊断。[/yellow]")
            break


def main():
    with console.status("[bold green]正在加载知识库...[/bold green]"):
        documents, sources = load_documents()

    diagnoser = ErrorDiagnoser()

    show_welcome()
    console.print(f"[green]已加载文档数量：[/green]{len(documents)}")

    while True:
        try:
            question = Prompt.ask("\n[bold cyan]请输入问题[/bold cyan]")

            if question.lower() == "quit":
                console.print("[yellow]已退出 HPC Agent。[/yellow]")
                break

            if not question.strip():
                continue

            intent = detect_intent(question)

            console.rule("[bold blue]处理请求")
            show_intent(intent)

            if intent == "diagnose_error":
                handle_diagnose_error(diagnoser, question)

            elif intent == "submit_job":
                handle_submit_job(question)

            elif intent == "submit_vasp_job":
                handle_submit_vasp_job(question)

            elif intent == "create_vasp_inputs":
                handle_create_vasp_inputs(question)

            elif intent == "import_vasp_inputs":
                handle_import_vasp_inputs(question)

            elif intent == "assist_vasp_inputs":
                handle_assist_vasp_inputs(question)

            elif intent == "register_vasp_job":
                handle_register_vasp_job(question)

            elif intent == "job_status":
                handle_job_query(question, query_job_status, "作业状态")

            elif intent == "job_output":
                handle_job_query(question, query_job_output, "作业输出")

            elif intent == "job_error":
                handle_job_query(question, query_job_error, "作业错误日志")

            elif intent == "list_remote_jobs":
                handle_list_remote_jobs()

            elif intent == "cleanup_remote_job":
                handle_cleanup_remote_job(question)

            elif intent == "cleanup_all_remote_jobs":
                handle_cleanup_all_remote_jobs()

            elif intent == "generate_sbatch":
                handle_generate_sbatch(question)

            elif intent == "generate_vasp_job":
                handle_generate_vasp_job(question)

            elif intent == "suggest_params":
                handle_suggest_params(question)

            elif intent == "troubleshoot_job":
                handle_troubleshoot_job(question, documents, sources)

            else:
                handle_rag_qa(question, documents, sources)

        except KeyboardInterrupt:
            console.print("\n[yellow]当前任务已中断，请重新输入指令。[/yellow]")
            continue


if __name__ == "__main__":
    main()
