from modules.knowledge_base import load_documents, retrieve, ask_llm
from modules.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters
from modules.error_diagnoser import ErrorDiagnoser


def detect_intent(question: str) -> str:
    q = question.lower()

    if any(word in q for word in ["生成脚本", "写脚本", "sbatch脚本", "slurm脚本", "script"]):
        return "generate_script"

    if any(word in q for word in ["参数建议", "建议参数", "怎么设置参数", "需要多少", "申请几个"]):
        return "suggest_parameters"
    
    if any(word in q for word in ["错误", "报错", "日志", "error", "failed", "killed", "denied", "oom", "log"]):
        return "diagnose_error"

    return "rag_qa"


def main():
    documents, sources = load_documents()
    diagnoser = ErrorDiagnoser()

    print("HPC Agent 已启动")
    print("支持功能：")
    print("1. Slurm 知识库问答")
    print("2. Slurm sbatch 脚本生成")
    print("3. Slurm 参数建议")
    print("4. 错误日志诊断")
    print("输入 quit 退出,或按 Ctrl+C 中断当前操作\n")

    while True:
        try:
            question = input("\n请输入问题(quit为退出）：").strip()

            if question.lower() == "quit":
                break

            intent = detect_intent(question)

            print("\n" + "=" * 60)

            if intent == "diagnose_error":
                print("\n已进入错误诊断模式")
                print("粘贴错误日志进行诊断")
                print("输入 quit 返回主菜单")
                print("如果想中断当前操作，按 Ctrl+C")

                while True:
                    try:
                        log_text = input("\nerror-log>(quit退出) ").strip()

                        if log_text.lower() == "quit":
                            print("已退出错误诊断模式")
                            break

                        results = diagnoser.diagnose(log_text)

                        print()
                        print(diagnoser.format_results(results))

                        if results:
                            choice = input("\n是否要根据该错误自动修复 sbatch 脚本？(y/n): ").strip().lower()

                            if choice == "y":
                                print("\n请粘贴 sbatch 脚本。")
                                print("粘贴完成后，输入 END 结束：")
                                print("如果想取消粘贴，按 Ctrl+C")

                                script_lines = []

                                while True:
                                    try:
                                        line = input()

                                        if line.strip() == "END":
                                            break

                                        script_lines.append(line)

                                    except KeyboardInterrupt:
                                        print("\n已取消 sbatch 脚本粘贴。")
                                        script_lines = []
                                        break

                                if script_lines:
                                    original_script = "\n".join(script_lines)
                                    fixed_script = diagnoser.fix_sbatch_script(original_script, results)

                                    print("\n修复后的 sbatch 脚本：")
                                    print("-" * 60)
                                    print(fixed_script)
                                    print("-" * 60)

                    except KeyboardInterrupt:
                        print("\n已中断当前错误诊断，请重新粘贴日志，或输入 quit 返回主菜单。")
                        continue

            elif intent == "generate_script":
                script = generate_sbatch_script(question)
                print("生成的 Slurm 脚本：\n")
                print(script)

            elif intent == "suggest_parameters":
                suggestion = suggest_slurm_parameters(question)
                print(suggestion)

            else:
                retrieved_docs = retrieve(question, documents, sources)
                answer = ask_llm(question, retrieved_docs)
                print(answer)

            print("=" * 60)

        except KeyboardInterrupt:
            print("\n当前任务已中断，请重新输入指令。")
            continue


if __name__ == "__main__":
    main()