"""LLM 호출. ChatOpenAI는 모듈 싱글턴으로 만든다 (DEV_04 1절 12번)."""
import logging
from functools import lru_cache

import openai
from langchain_openai import ChatOpenAI

from app.rag import config_rag
from app.rag.errors import ApiError
from app.rag.schemas import AnswerDraft

logger = logging.getLogger("rag")


def is_reasoning_model(model: str) -> bool:
    """gpt-5 이후·o 시리즈는 temperature를 기본값(1)만 받고 reasoning_effort를 받는다."""
    return model.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4"))


@lru_cache(maxsize=4)
def get_llm(model: str | None = None, reasoning_effort: str | None = None) -> ChatOpenAI:
    model = model or config_rag.LLM_MODEL
    reasoning = is_reasoning_model(model)
    return ChatOpenAI(
        model=model,
        api_key=config_rag.LLM_API_KEY,
        base_url=config_rag.LLM_BASE_URL,
        temperature=None if reasoning else config_rag.LLM_TEMPERATURE,
        reasoning_effort=(reasoning_effort or config_rag.LLM_REASONING_EFFORT) if reasoning else None,
        timeout=30,
        max_retries=1,
    )


def generate(system: str, user: str, images: list[tuple[str, str]] | None = None) -> tuple[AnswerDraft, int, int]:
    """구조화 출력으로 답변 초안을 받는다. 반환: (draft, 입력 토큰, 출력 토큰).

    images: [(근거 라벨, PNG base64)]. 있으면 사용자 메시지에 페이지 이미지를 함께 넣고 LLM_IMAGE_MODEL로 부른다.
    """
    model = get_llm(config_rag.LLM_IMAGE_MODEL, config_rag.LLM_IMAGE_REASONING_EFFORT) if images else get_llm()
    chain = model.with_structured_output(AnswerDraft, include_raw=True)
    human: str | list = user
    if images:
        human = [{"type": "text", "text": user}]
        for label, b64 in images:
            human.append({"type": "text", "text": f"[{label}] 원본 페이지"})
            human.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}})
    try:
        out = chain.invoke([("system", system), ("human", human)])
    except (openai.APITimeoutError, openai.APIConnectionError):
        raise ApiError(503, "UPSTREAM_TIMEOUT", "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.")
    except Exception as e:
        # 내부 메시지는 클라이언트에 노출하지 않고 예외 종류만 기록한다
        logger.error("llm call failed: %s", type(e).__name__)
        raise ApiError(500, "INTERNAL_ERROR", "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")

    draft = out.get("parsed")
    if draft is None:
        logger.error("llm structured output parse failed")
        raise ApiError(500, "INTERNAL_ERROR", "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")
    usage = getattr(out.get("raw"), "usage_metadata", None) or {}
    return draft, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
