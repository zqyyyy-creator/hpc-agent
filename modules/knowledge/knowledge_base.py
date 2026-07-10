import os
import re
import math
from collections import Counter

import jieba
from dotenv import load_dotenv
from openai import OpenAI

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from modules.core.paths import ENV_PATH, HPC_DOCUMENTS_DIR

def _sanitize_text(text: str) -> str:
    """清除 UTF-8 surrogate 字符，防止序列化时报错。

    在 WSL / Windows 文件系统等场景下，Python 可能通过
    surrogateescape 错误处理策略将无效字节解码为 surrogate
    字符（U+D800–U+DFFF），这些字符无法被 UTF-8 编码器处理，
    会导致 openai SDK 序列化 JSON 时抛出 UnicodeEncodeError。
    """
    return text.encode("utf-8", errors="replace").decode("utf-8")


# 加载 .env
load_dotenv(ENV_PATH)


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
_MAX_CHUNK_CHARS = 1800
_KEYWORD_WEIGHT = 0.75
_SEMANTIC_WEIGHT = 0.25
_BM25_K1 = 1.5
_BM25_B = 0.75
_TFIDF_WEIGHT = 0.45
_BM25_WEIGHT = 0.55
_TITLE_WEIGHT = 2.0
_KEYWORDS_WEIGHT = 1.6
_BODY_WEIGHT = 1.0
_MAX_CHUNKS_PER_FILE = 2
_STOPWORDS = {
    "什么",
    "怎么",
    "如何",
    "一下",
    "这个",
    "那个",
    "我的",
    "可以",
    "需要",
    "使用",
    "查看",
    "作业",
    "超算",
}

_TOPIC_KEYWORDS = {
    "cluster": {
        "all",
        "amd_256",
        "amd_test",
        "bscc-a",
        "partition",
        "queue",
        "sinfo",
        "scontrol",
        "节点",
        "分区",
        "队列",
    },
    "pending": {
        "pd",
        "pending",
        "resources",
        "priority",
        "dependency",
        "reqnodenotavail",
        "排队",
        "不运行",
        "等待",
        "卡住",
    },
    "gpu": {
        "gpu",
        "cuda",
        "nvidia-smi",
        "gres",
        "cuda_visible_devices",
        "显卡",
        "显存",
    },
    "environment": {
        "module",
        "conda",
        "python",
        "path",
        "module-not-found",
        "modulenotfounderror",
        "环境",
        "软件",
    },
    "storage": {
        "quota",
        "disk",
        "storage",
        "scratch",
        "df",
        "du",
        "配额",
        "磁盘",
        "空间",
    },
    "logs": {
        "stdout",
        "stderr",
        "output",
        "error",
        "tail",
        "日志",
        "输出",
        "报错",
    },
    "vasp": {
        "vasp",
        "incar",
        "poscar",
        "potcar",
        "kpoints",
        "outcar",
        "oszicar",
        "wavecar",
        "chgcar",
        "结构优化",
        "静态",
        "能带",
        "态密度",
    },
    "slurm": {
        "slurm",
        "sbatch",
        "squeue",
        "sacct",
        "scancel",
        "#SBATCH",
        "作业",
        "提交",
    },
}

_QUERY_EXPANSIONS = {
    "卡住": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "不动": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "不运行": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "没开始": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "排队": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "一直pd": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "一直pending": ["pending", "PD", "Resources", "Priority", "squeue", "scontrol"],
    "没输出": ["stdout", "stderr", "output", "error", "tail", "%x_%j.out", "%x_%j.err"],
    "没有输出": ["stdout", "stderr", "output", "error", "tail", "%x_%j.out", "%x_%j.err"],
    "日志": ["stdout", "stderr", "output", "error", "tail", "sacct"],
    "报错": ["stderr", "error", "traceback", "tail", "sacct"],
    "显卡": ["GPU", "CUDA", "nvidia-smi", "CUDA_VISIBLE_DEVICES", "gres"],
    "gpu不可用": ["CUDA", "nvidia-smi", "CUDA_VISIBLE_DEVICES", "gres"],
    "找不到gpu": ["CUDA", "nvidia-smi", "CUDA_VISIBLE_DEVICES", "gres"],
    "显存": ["CUDA out of memory", "GPU", "nvidia-smi"],
    "环境": ["module", "conda", "PATH", "which python", "module list"],
    "包找不到": ["ModuleNotFoundError", "module", "conda", "python"],
    "conda不生效": ["conda activate", "source conda.sh", "module", "PATH"],
    "队列": ["partition", "sinfo", "scontrol show partition"],
    "分区": ["partition", "sinfo", "scontrol show partition"],
    "能跑多久": ["TIMELIMIT", "MaxTime", "partition", "sinfo"],
    "时间限制": ["TIMELIMIT", "MaxTime", "partition", "sinfo"],
    "配额": ["quota", "df -h", "du -sh", "disk quota exceeded"],
    "磁盘满": ["quota", "df -h", "du -sh", "No space left on device"],
    "空间满": ["quota", "df -h", "du -sh", "No space left on device"],
    "势函数": ["POTCAR", "POSCAR", "VASP"],
    "赝势": ["POTCAR", "POSCAR", "VASP"],
    "算到一半": ["VASP", "OUTCAR", "OSZICAR", "sacct", "OOM", "TIMEOUT"],
}
_TOPICS_FOR_QUERY_EXPANSION = {
    "cluster",
    "pending",
    "gpu",
    "environment",
    "storage",
    "logs",
    "slurm",
}


def _split_metadata_values(value: str) -> list[str]:
    return [
        item.strip().lower()
        for item in re.split(r"[,，\s]+", value)
        if item.strip()
    ]


def _extract_document_metadata(text: str) -> dict[str, str | list[str]]:
    title = ""
    keywords = []
    topics = []
    metadata: dict[str, str] = {}
    in_keywords = False
    in_metadata = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if in_keywords:
                in_keywords = False
            if in_metadata:
                in_metadata = False
            continue

        if line.startswith("元数据："):
            in_metadata = True
            in_keywords = False
            continue

        if in_metadata:
            match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)\s*[:：]\s*(.+)", line)
            if match:
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                metadata[key] = value
                if key in {"topic", "topics"}:
                    topics.extend(_split_metadata_values(value))
                continue
            in_metadata = False

        if line.startswith("标题："):
            title = line.removeprefix("标题：").strip()
            continue

        if line.startswith("关键词："):
            in_keywords = True
            tail = line.removeprefix("关键词：").strip()
            if tail:
                keywords.append(tail)
            continue

        if in_keywords:
            if line.endswith("：") or line in {"说明：", "基本命令："}:
                in_keywords = False
                continue
            keywords.append(line)

    return {
        "title": title,
        "keywords": " ".join(keywords),
        "topics": sorted(set(topics)),
        "scope": metadata.get("scope", ""),
        "dynamic": metadata.get("dynamic", ""),
    }


def _build_chunk_prefix(metadata: dict[str, str | list[str]]) -> str:
    parts = []
    title = str(metadata.get("title") or "")
    keywords = str(metadata.get("keywords") or "")
    topics = metadata.get("topics") or []
    scope = str(metadata.get("scope") or "")
    dynamic = str(metadata.get("dynamic") or "")

    if title:
        parts.append(f"文档标题：{title}")
    if topics:
        parts.append(f"文档主题：{', '.join(topics)}")
    if scope:
        parts.append(f"文档范围：{scope}")
    if dynamic:
        parts.append(f"动态信息：{dynamic}")
    if keywords:
        parts.append(f"文档关键词：{keywords}")
    return "\n".join(parts)


def _strip_metadata_block(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "元数据：":
        return text

    index = 1
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            break
        if not re.match(r"[A-Za-z_][A-Za-z0-9_-]*\s*[:：]", line):
            break
        index += 1

    return "\n".join(lines[index:]).lstrip()


def _chunk_document(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """Create retrieval chunks while preserving document-level context.

    The knowledge files are written as small labeled paragraphs. Splitting only on
    blank lines makes chunks such as "关键词：" or "常见命令：" too thin, so we
    merge adjacent paragraphs and prepend title/keywords to each chunk.
    """
    metadata = _extract_document_metadata(text)
    prefix = _build_chunk_prefix(metadata)
    text_without_metadata = _strip_metadata_block(text)
    parts = [
        part.strip()
        for part in re.split(r"\n\s*\n", text_without_metadata)
        if part.strip() and part.strip() != "---"
    ]

    if not parts:
        return []

    chunks = []
    current = []

    for part in parts:
        candidate_body = "\n\n".join(current + [part])
        candidate = f"{prefix}\n\n{candidate_body}" if prefix else candidate_body

        if current and len(candidate) > max_chars:
            body = "\n\n".join(current)
            chunks.append(f"{prefix}\n\n{body}" if prefix else body)
            current = [part]
        else:
            current.append(part)

    if current:
        body = "\n\n".join(current)
        chunks.append(f"{prefix}\n\n{body}" if prefix else body)

    return chunks


def _tokenize_for_boost(text: str) -> set[str]:
    tokens = set()
    lowered = text.lower()

    for token in jieba.lcut(lowered):
        token = token.strip()
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.add(token)

    for token in re.findall(r"[a-z0-9_./:+-]{2,}", lowered):
        if token not in _STOPWORDS:
            tokens.add(token)

    return tokens


def _tokenize_for_search(text: str) -> list[str]:
    tokens = []
    lowered = text.lower()

    for token in jieba.lcut(lowered):
        token = token.strip()
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.append(token)

    for token in re.findall(r"[a-z0-9_./:%#+-]{2,}", lowered):
        if token not in _STOPWORDS:
            tokens.append(token)

    return tokens


def expand_query(query: str) -> str:
    normalized = query.lower().replace(" ", "")
    additions = []

    for trigger, terms in _QUERY_EXPANSIONS.items():
        if trigger.lower().replace(" ", "") in normalized:
            additions.extend(terms)

    for topic in _query_topics(query):
        if topic not in _TOPICS_FOR_QUERY_EXPANSION:
            continue
        additions.extend(sorted(_TOPIC_KEYWORDS.get(topic, set())))

    if not additions:
        return query

    seen = set()
    unique_additions = []
    for term in additions:
        key = term.lower()
        if key not in seen and key not in normalized:
            seen.add(key)
            unique_additions.append(term)

    return query + " " + " ".join(unique_additions)


def _keyword_boost(query: str, document: str) -> float:
    query_tokens = _tokenize_for_boost(expand_query(query))
    if not query_tokens:
        return 0.0

    document_tokens = _tokenize_for_boost(document[:1200])
    overlap = query_tokens & document_tokens

    if not overlap:
        return 0.0

    return min(len(overlap) / len(query_tokens) * 0.2, 0.2)


def _query_topics(query: str) -> set[str]:
    tokens = _tokenize_for_boost(query)
    topics = set()

    for topic, keywords in _TOPIC_KEYWORDS.items():
        if tokens & keywords:
            topics.add(topic)

    return topics


def _topics_for_document(document: str) -> set[str]:
    match = re.search(r"^文档主题：(.+)$", document, re.MULTILINE)
    if not match:
        return set()
    return set(_split_metadata_values(match.group(1)))


def _metadata_boost(query: str, source: str, document: str) -> float:
    query_topics = _query_topics(query)
    if not query_topics:
        return 0.0

    document_topics = _topics_for_document(document)
    query_tokens = _tokenize_for_boost(query)
    document_tokens = _tokenize_for_boost(document[:1000])

    boost = 0.0
    for topic in query_topics:
        topic_terms = _TOPIC_KEYWORDS.get(topic, set())
        if topic in document_topics:
            boost += 0.10 if len(document_topics) <= 2 else 0.06
        elif document_tokens & topic_terms:
            boost += 0.03

    if "cluster" in document_topics and query_tokens & {"partition", "分区", "队列", "amd_256", "amd_test"}:
        boost += 0.06

    return min(boost, 0.18)


def _retrieval_cache_key(documents, sources):
    return tuple(zip(sources, documents))


def _extract_prefixed_field(document: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}：(.+)$", document, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _document_body(document: str) -> str:
    lines = [
        line
        for line in document.splitlines()
        if not line.startswith(("文档标题：", "文档主题：", "文档范围：", "动态信息：", "文档关键词："))
    ]
    return "\n".join(lines)


def _weighted_document_text(document: str) -> str:
    title = _extract_prefixed_field(document, "文档标题")
    keywords = _extract_prefixed_field(document, "文档关键词")
    topics = _extract_prefixed_field(document, "文档主题")
    body = _document_body(document)

    weighted_parts = []
    weighted_parts.extend([title, topics] * int(_TITLE_WEIGHT))
    weighted_parts.extend([keywords] * int(_KEYWORDS_WEIGHT))
    weighted_parts.append(body)
    return "\n".join(part for part in weighted_parts if part)


def _minmax_normalize(scores: list[float]) -> list[float]:
    if not scores:
        return []
    min_score = min(scores)
    max_score = max(scores)
    if math.isclose(min_score, max_score):
        return [1.0 if score > 0 else 0.0 for score in scores]
    return [(score - min_score) / (max_score - min_score) for score in scores]


def _get_keyword_index(documents, sources):
    cache_key = _retrieval_cache_key(documents, sources)

    if cache_key in _RETRIEVAL_CACHE:
        return _RETRIEVAL_CACHE[cache_key]

    weighted_documents = [_weighted_document_text(document) for document in documents]
    vectorizer = TfidfVectorizer(
        tokenizer=jieba.lcut,
        token_pattern=None
    )

    doc_vectors = vectorizer.fit_transform(weighted_documents)

    tokenized_documents = [_tokenize_for_search(document) for document in weighted_documents]
    doc_freqs: Counter[str] = Counter()
    for tokens in tokenized_documents:
        doc_freqs.update(set(tokens))

    doc_lengths = [len(tokens) for tokens in tokenized_documents]
    avg_doc_len = sum(doc_lengths) / len(doc_lengths) if doc_lengths else 0.0

    index = {
        "vectorizer": vectorizer,
        "doc_vectors": doc_vectors,
        "tokenized_documents": tokenized_documents,
        "doc_freqs": doc_freqs,
        "doc_lengths": doc_lengths,
        "avg_doc_len": avg_doc_len,
        "doc_count": len(tokenized_documents),
    }
    _RETRIEVAL_CACHE[cache_key] = index
    return index


def _bm25_scores(query: str, index: dict) -> list[float]:
    query_terms = _tokenize_for_search(query)
    doc_count = index["doc_count"]
    avg_doc_len = index["avg_doc_len"] or 1.0
    doc_freqs = index["doc_freqs"]
    tokenized_documents = index["tokenized_documents"]
    doc_lengths = index["doc_lengths"]
    scores = []

    for doc_index, tokens in enumerate(tokenized_documents):
        term_counts = Counter(tokens)
        doc_len = doc_lengths[doc_index] or 1
        score = 0.0

        for term in query_terms:
            freq = term_counts.get(term, 0)
            if freq == 0:
                continue

            df = doc_freqs.get(term, 0)
            idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
            denominator = freq + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_len / avg_doc_len)
            score += idf * (freq * (_BM25_K1 + 1) / denominator)

        scores.append(score)

    return scores


# 读取 data 文件夹里的所有 txt 文档
def load_documents():

    docs_path = HPC_DOCUMENTS_DIR

    chunks = []
    sources = []

    for path in docs_path.glob("*.txt"):

        text = path.read_text(encoding="utf-8", errors="replace")

        for i, chunk in enumerate(_chunk_document(text)):
            chunks.append(chunk)
            sources.append(f"{path.name}#chunk{i}")

    return chunks, sources

def keyword_retrieve(query, documents, sources, top_k=8, min_score=0.01):
    expanded_query = expand_query(query)
    index = _get_keyword_index(documents, sources)
    vectorizer = index["vectorizer"]
    doc_vectors = index["doc_vectors"]
    query_vector = vectorizer.transform([expanded_query])

    similarities = cosine_similarity(query_vector, doc_vectors)[0]
    bm25_raw_scores = _bm25_scores(expanded_query, index)
    bm25_scores = _minmax_normalize(bm25_raw_scores)
    keyword_scores = []

    for index, document in enumerate(documents):
        source = sources[index]
        tfidf_score = float(similarities[index])
        bm25_score = bm25_scores[index] if index < len(bm25_scores) else 0.0
        lexical_boost = _keyword_boost(expanded_query, document)
        metadata_boost = _metadata_boost(query, source, document)
        combined_keyword_score = (
            _TFIDF_WEIGHT * tfidf_score
            + _BM25_WEIGHT * bm25_score
        )
        score = combined_keyword_score + lexical_boost + metadata_boost

        keyword_scores.append({
            "source": source,
            "content": document,
            "score": score,
            "keyword_score": score,
            "tfidf_score": tfidf_score,
            "bm25_score": bm25_score,
            "lexical_boost": lexical_boost,
            "metadata_boost": metadata_boost,
            "retrieval": "keyword",
        })

    ranked_results = sorted(
        keyword_scores,
        key=lambda result: result["score"],
        reverse=True,
    )

    return [
        result
        for result in ranked_results
        if result["score"] >= min_score
    ][:top_k]


def semantic_retrieve(query, documents, sources, top_k=8, min_score=0.01):
    """Placeholder for embedding/vector retrieval.

    The project currently avoids a mandatory embedding service or vector
    database. Keeping this function in the pipeline makes the RAG flow
    hybrid-ready: a future implementation can return the same result shape with
    ``semantic_score`` populated.
    """
    return []


def _merge_ranked_results(keyword_results, semantic_results, top_k=3, min_score=0.05):
    merged = {}

    for result in keyword_results:
        source = result["source"]
        merged[source] = {
            "source": source,
            "content": result["content"],
            "keyword_score": result.get("keyword_score", result["score"]),
            "semantic_score": 0.0,
            "tfidf_score": result.get("tfidf_score", 0.0),
            "bm25_score": result.get("bm25_score", 0.0),
            "lexical_boost": result.get("lexical_boost", 0.0),
            "metadata_boost": result.get("metadata_boost", 0.0),
            "retrieval": "keyword",
        }

    for result in semantic_results:
        source = result["source"]
        item = merged.setdefault(
            source,
            {
                "source": source,
                "content": result["content"],
                "keyword_score": 0.0,
                "semantic_score": 0.0,
                "tfidf_score": 0.0,
                "bm25_score": 0.0,
                "lexical_boost": 0.0,
                "metadata_boost": 0.0,
                "retrieval": "semantic",
            },
        )
        item["semantic_score"] = max(
            item.get("semantic_score", 0.0),
            result.get("semantic_score", result.get("score", 0.0)),
        )
        if item["retrieval"] == "keyword":
            item["retrieval"] = "hybrid"

    ranked_results = []
    for item in merged.values():
        final_score = (
            _KEYWORD_WEIGHT * item.get("keyword_score", 0.0)
            + _SEMANTIC_WEIGHT * item.get("semantic_score", 0.0)
        )
        item["score"] = final_score
        ranked_results.append(item)

    ranked_results.sort(key=lambda result: result["score"], reverse=True)

    filtered_results = [
        result
        for result in ranked_results
        if result["score"] >= min_score
    ]
    return _diversify_results(filtered_results, top_k=top_k)


def _source_file(source: str) -> str:
    return source.split("#", 1)[0]


def _diversify_results(results: list[dict], top_k=3, max_per_file: int = _MAX_CHUNKS_PER_FILE):
    selected = []
    per_file_counts: Counter[str] = Counter()
    deferred = []

    for result in results:
        source_file = _source_file(result["source"])
        if per_file_counts[source_file] < max_per_file:
            selected.append(result)
            per_file_counts[source_file] += 1
        else:
            deferred.append(result)

        if len(selected) >= top_k:
            return selected

    for result in deferred:
        selected.append(result)
        if len(selected) >= top_k:
            break

    return selected


# Hybrid-ready 检索：当前启用 TF-IDF/BM25-like 关键词检索 + metadata boost，
# 并预留 semantic_retrieve 接口用于后续 embedding/vector 检索。
def retrieve(query, documents, sources, top_k=3, min_score=0.05):
    keyword_results = keyword_retrieve(
        query,
        documents,
        sources,
        top_k=max(top_k * 4, 8),
        min_score=0.01,
    )
    semantic_results = semantic_retrieve(
        query,
        documents,
        sources,
        top_k=max(top_k * 4, 8),
        min_score=0.01,
    )
    return _merge_ranked_results(
        keyword_results,
        semantic_results,
        top_k=top_k,
        min_score=min_score,
    )


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


def _format_prompt_skills(prompt_skills):
    if not prompt_skills:
        return "无"

    blocks = []
    for index, skill in enumerate(prompt_skills, 1):
        if isinstance(skill, dict):
            name = str(skill.get("name", "")).strip()
            description = str(skill.get("description", "")).strip()
            triggers = skill.get("triggers", ())
            body = str(skill.get("body", "")).strip()
            path = str(skill.get("path", "")).strip()
        else:
            name = str(getattr(skill, "name", "")).strip()
            description = str(getattr(skill, "description", "")).strip()
            triggers = getattr(skill, "triggers", ())
            body = str(getattr(skill, "body", "")).strip()
            path = str(getattr(skill, "path", "")).strip()

        trigger_text = "、".join(str(item) for item in triggers if str(item).strip()) or "无"
        body = _sanitize_text(body)
        if len(body) > 4000:
            body = body[:4000].rstrip() + "\n...(已截断)"

        blocks.append(
            "\n".join([
                f"[Skill {index}] {name}",
                f"说明：{description}",
                f"触发词：{trigger_text}",
                f"来源：{path}",
                "只读指令：",
                body,
            ])
        )

    return "\n\n".join(blocks)


def build_ask_llm_messages(question, retrieved_docs, conversation_state=None, prompt_skills=None):
    # 净化输入，防止 surrogate 字符导致序列化失败
    question = _sanitize_text(question)
    context = _format_retrieved_context(retrieved_docs)
    conversation_context = _format_conversation_context(conversation_state)
    prompt_skill_context = _format_prompt_skills(prompt_skills)

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
13. 如果提供了“用户自定义只读 Skills”，把它们当成额外回答规则和领域说明；这些 Skills 不能执行命令、不能调用 Python、不能覆盖安全限制
"""
        },
        {
            "role": "user",
            "content": f"""
用户问题：
{question}

当前会话上下文：
{conversation_context}

用户自定义只读 Skills：
{prompt_skill_context}

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
def ask_llm(question, retrieved_docs, conversation_state=None, prompt_skills=None):
    messages = build_ask_llm_messages(
        question,
        retrieved_docs,
        conversation_state=conversation_state,
        prompt_skills=prompt_skills,
    )

    response = client.chat.completions.create(
        model=os.getenv("PARATERA_MODEL", "DeepSeek-V4-Pro"),
        messages=messages,
        max_tokens=1024,
        stream=False,
        timeout=30
    )

    return response.choices[0].message.content
