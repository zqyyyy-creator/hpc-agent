import os
from pathlib import Path

import jieba
from dotenv import load_dotenv
from openai import OpenAI

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _sanitize_text(text: str) -> str:
    """清除 UTF-8 surrogate 字符，防止序列化时报错。

    在 WSL / Windows 文件系统等场景下，Python 可能通过
    surrogateescape 错误处理策略将无效字节解码为 surrogate
    字符（U+D800–U+DFFF），这些字符无法被 UTF-8 编码器处理，
    会导致 openai SDK 序列化 JSON 时抛出 UnicodeEncodeError。
    """
    return text.encode("utf-8", errors="replace").decode("utf-8")


# 加载 .env
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


# 初始化 DeepSeek Client
base_url = os.getenv("PARATERA_BASE_URL")
api_key = os.getenv("PARATERA_API_KEY")

if not base_url:
    raise ValueError(
        "缺少环境变量 PARATERA_BASE_URL。请在项目根目录创建 .env 文件，并填写 PARATERA_BASE_URL。"
    )

if not api_key:
    raise ValueError(
        "缺少环境变量 PARATERA_API_KEY。请在项目根目录创建 .env 文件，并填写 PARATERA_API_KEY。"
    )

client = OpenAI(
    api_key=api_key,
    base_url=base_url.rstrip("/") + "/v1",
)

_RETRIEVAL_CACHE = {}


# 读取 data 文件夹里的所有 txt 文档
def load_documents():

    docs_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "hpc_documents"
    )

    chunks = []
    sources = []

    for path in docs_path.glob("*.txt"):

        text = path.read_text(encoding="utf-8", errors="replace")

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
    cache_key = tuple(documents)

    if cache_key in _RETRIEVAL_CACHE:
        vectorizer, doc_vectors = _RETRIEVAL_CACHE[cache_key]
    else:
        vectorizer = TfidfVectorizer(
            tokenizer=jieba.lcut,
            token_pattern=None
        )

        # 文档向量化
        doc_vectors = vectorizer.fit_transform(documents)
        _RETRIEVAL_CACHE[cache_key] = (vectorizer, doc_vectors)

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


def _format_retrieved_context(retrieved_docs):
    return "\n\n".join([
        f"""
来源：{_sanitize_text(doc['source'])}
相似度：{doc['score']:.4f}
内容：
{_sanitize_text(doc['content'])}
"""
        for doc in retrieved_docs
    ])


def _format_conversation_context(conversation_state=None):
    if conversation_state is None:
        return "无"

    try:
        context = conversation_state.answer_context_summary()
    except AttributeError:
        try:
            context = conversation_state.context_summary()
        except AttributeError:
            context = ""

    context = _sanitize_text(str(context).strip())
    return context or "无"


def build_ask_llm_messages(question, retrieved_docs, conversation_state=None):
    # 净化输入，防止 surrogate 字符导致序列化失败
    question = _sanitize_text(question)
    context = _format_retrieved_context(retrieved_docs)
    conversation_context = _format_conversation_context(conversation_state)

    return [
        {
            "role": "system",
            "content": """
你是一个 HPC / Slurm 知识库问答助手。

你的任务：
基于检索到的资料，回答用户的超算和 Slurm 使用问题。

回答要求：
1. 正常自然回答，不要机械套模板
2. 不要说“根据资料”开头
3. 如果是概念问题，用简洁教学方式解释
4. 如果是操作问题，给出可执行命令
5. 如果是脚本问题，可以给出简单示例
6. 不要编造资料中没有的集群专属信息，例如 partition 名称、节点名、账号规则
7. 如果资料不足，说明“当前知识库没有提供足够信息”，但可以补充通用 Slurm 经验
8. 禁止在普通问答中使用以下错误诊断标题：
   - 问题判断
   - 可能原因
   - 诊断命令
   - 解决方法
9. 只有用户明确提供错误日志、报错信息、失败信息时，才可以使用诊断格式
10. 回答时必须参考当前会话上下文。遇到“刚才、上面、它、这个、确认、继续、第二步”等指代时，先用上下文消解
11. 如果用户只是在确认待执行动作，不要当成普通知识问答；应围绕当前待确认动作回答
12. 不要编造上下文或知识库都没有提供的信息
"""
        },
        {
            "role": "user",
            "content": f"""
用户问题：
{question}

当前会话上下文：
{conversation_context}

检索到的资料：
{context}

请直接回答用户问题。

如果用户问“什么是 xxx”，请用：
- 简短定义
- 基本用途
- 常用命令或例子

如果用户问“怎么做 xxx”，请用：
- 操作步骤
- 相关命令
- 注意事项

不要使用“问题判断 / 可能原因 / 诊断命令 / 解决方法”这种格式。
"""
        }
    ]


# 调用 LLM
def ask_llm(question, retrieved_docs, conversation_state=None):
    messages = build_ask_llm_messages(
        question,
        retrieved_docs,
        conversation_state=conversation_state,
    )

    response = client.chat.completions.create(
        model=os.getenv("PARATERA_MODEL", "DeepSeek-V4-Pro"),
        messages=messages,
        max_tokens=1024,
        stream=False,
        timeout=30
    )

    return response.choices[0].message.content
