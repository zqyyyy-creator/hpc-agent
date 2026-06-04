import os
from pathlib import Path

import jieba
from dotenv import load_dotenv
from openai import OpenAI

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# 加载 .env
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# 初始化 DeepSeek Client
client = OpenAI(
    api_key=os.getenv("PARATERA_API_KEY"),
    base_url=os.getenv("PARATERA_BASE_URL") + "/v1",
    timeout=60,
)


# 读取 data 文件夹里的所有 txt 文档
def load_documents():

    docs_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "hpc_documents"
    )

    chunks = []
    sources = []

    for path in docs_path.glob("*.txt"):

        text = path.read_text(encoding="utf-8")

        # chunking
        parts = text.split("\n\n")

        for i, part in enumerate(parts):

            part = part.strip()

            if part:

                chunks.append(part)
                sources.append(f"{path.name}#chunk{i}")

    return chunks, sources

# TF-IDF 检索
def retrieve(query, documents, sources, top_k=3, min_score=0.05):

    vectorizer = TfidfVectorizer(
        tokenizer=jieba.lcut,
        token_pattern=None
    )

    # 文档向量化
    doc_vectors = vectorizer.fit_transform(documents)

    # 用户问题向量化
    query_vector = vectorizer.transform([query])

    # 计算 cosine similarity
    similarities = cosine_similarity(query_vector, doc_vectors)[0]

    # 相似度排序
    ranked_indices = similarities.argsort()[::-1]

    results = []

    for index in ranked_indices:

        if similarities[index] >= min_score:

            results.append({
                "source": sources[index],
                "content": documents[index],
                "score": similarities[index]
            })

        if len(results) >= top_k:
            break

    return results


# 调用 LLM
def ask_llm(question, retrieved_docs):

    context = "\n\n".join([
        f"""
来源：{doc['source']}
相似度：{doc['score']:.4f}
内容：
{doc['content']}
"""
        for doc in retrieved_docs
    ])

    messages = [
        {
            "role": "system",
            "content": """
你是一个 HPC / Slurm 技术支持助手。

你的任务：
基于检索到的资料，回答用户的超算使用问题。

回答要求：
1. 不要只复述资料
2. 不要说“根据资料”开头
3. 必须把答案组织成技术支持格式
4. 如果涉及错误诊断，必须包含：
   - 问题判断
   - 可能原因
   - 诊断命令
   - 解决方法
5. 如果涉及 Slurm 操作，必须给出可执行命令
6. 不要编造资料中没有的集群专属信息，例如 partition 名称、节点名、账号规则
7. 如果资料不足，说明“当前知识库没有提供足够信息”，但仍可给出通用排查方向
"""
        },
        {
            "role": "user",
            "content": f"""
用户问题：
{question}

检索到的资料：
{context}

请按下面格式回答：

### 问题判断
用 1-2 句话判断用户遇到的问题。

### 可能原因
用编号列表列出原因。

### 诊断命令
给出可以直接复制运行的命令。

### 解决方法
给出具体修改建议或操作步骤。

### 补充说明
说明注意事项。如果知识库信息不足，请明确说明。
"""
        }
    ]

    response = client.chat.completions.create(
        model="DeepSeek-V4-Pro",
        messages=messages,
        max_tokens=1024,
        stream=False,
    )

    return response.choices[0].message.content


def main():

    # 加载知识库
    documents, sources = load_documents()

    print("Loaded documents:", len(documents))

    print("HPC RAG Agent 已启动")
    print()

    while True:

        question = input("请输入问题（输入 quit 退出）： ")

        if question.lower() == "quit":
            break

        # 检索
        retrieved_docs = retrieve(question, documents, sources)

        print("\n检索到的文档：")

        if not retrieved_docs:
            print("没有找到相关资料")
            continue

        for doc in retrieved_docs:
            print("=" * 50)
            print("来源：", doc["source"])
            print("相似度：", round(doc["score"], 4))
            print(doc["content"])

        # 调用 LLM
        answer = ask_llm(question, retrieved_docs)

        print("\nAI回答：")
        print(answer)
        print("\n")


if __name__ == "__main__":
    main()