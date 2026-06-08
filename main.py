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


def handle_troubleshoot_job(question, documents, sources):
    with console.status("[bold green]正在分析作业状态问题...[/bold green]"):
        retrieved_docs = retrieve(question, documents, sources)
        answer = ask_llm(question, retrieved_docs)

    console.print(Panel(Markdown(answer), title="作业排查建议", border_style="yellow"))


def handle_diagnose_error(diagnoser):
    console.print(
        Panel(
            "请粘贴完整错误日志。\n输入 [bold]quit[/bold] 返回主菜单。",
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
                handle_diagnose_error(diagnoser)

            elif intent == "generate_sbatch":
                handle_generate_sbatch(question)

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