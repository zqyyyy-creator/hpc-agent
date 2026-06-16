from dataclasses import dataclass

from modules.core.agent_runtime import execute_answer_intent
from modules.routing.tool_dispatcher import try_llm_dispatch


@dataclass
class LLMFallbackResult:
    intent: str
    answer: str
    source: str
    success: bool = True


def answer_redirect_intent(question, intent, documents, sources, diagnoser, state):
    result = execute_answer_intent(
        question,
        intent,
        documents=documents,
        sources=sources,
        diagnoser=diagnoser,
        state=state,
    )
    if result.handled:
        return result.answer

    return answer_rag_fallback(question, documents, sources, state)


def answer_rag_fallback(question, documents, sources, state, no_docs_message=None):
    return execute_answer_intent(
        question,
        "rag_qa",
        documents=documents,
        sources=sources,
        diagnoser=None,
        state=state,
        no_docs_message=no_docs_message,
    ).answer


def handle_llm_fallback(
    question,
    documents,
    sources,
    diagnoser,
    state,
    *,
    no_docs_message=None,
):
    llm_result = try_llm_dispatch(question, state=state)

    if llm_result is not None and llm_result.handled:
        if llm_result.data.get("llm_redirect"):
            intent = llm_result.intent
            return LLMFallbackResult(
                intent=intent,
                answer=answer_redirect_intent(
                    question,
                    intent,
                    documents,
                    sources,
                    diagnoser,
                    state,
                ),
                source="llm_redirect",
                success=True,
            )

        return LLMFallbackResult(
            intent=llm_result.intent,
            answer=llm_result.message,
            source="llm_message",
            success=llm_result.success,
        )

    return LLMFallbackResult(
        intent="rag_qa",
        answer=answer_rag_fallback(
            question,
            documents,
            sources,
            state,
            no_docs_message=no_docs_message,
        ),
        source="rag_qa",
        success=True,
    )
