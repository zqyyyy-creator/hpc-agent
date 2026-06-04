from modules.knowledge_base import load_documents, retrieve, ask_llm
from modules.slurm_assistant import generate_sbatch_script, suggest_slurm_parameters


def detect_intent(question: str) -> str:
    q = question.lower()

    if any(word in q for word in ["生成脚本", "写脚本", "sbatch脚本", "slurm脚本", "script"]):
        return "generate_script"

    if any(word in q for word in ["参数建议", "建议参数", "怎么设置参数", "需要多少", "申请几个"]):
        return "suggest_parameters"

    return "rag_qa"


def main():
    documents, sources = load_documents()

    print("HPC Agent 已启动")
    print("支持功能：")
    print("1. Slurm 知识库问答")
    print("2. Slurm sbatch 脚本生成")
    print("3. Slurm 参数建议")
    print("输入 quit 退出")

    while True:
        question = input("\n请输入问题(quit为退出）：").strip()

        if question.lower() == "quit":
            break

        intent = detect_intent(question)

        print("\n" + "=" * 60)

        if intent == "generate_script":
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


if __name__ == "__main__":
    main()