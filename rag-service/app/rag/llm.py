"""LLM 호출. ChatOpenAI는 모듈 싱글턴으로 만든다 (DEV_04 1절 12번)."""
import logging
from functools import lru_cache

import openai
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

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


def _invoke(model: ChatOpenAI, schema: type[BaseModel], messages: list) -> tuple[BaseModel, int, int]:
    """구조화 출력 호출의 공통부. 반환: (schema 인스턴스, 입력 토큰, 출력 토큰).

    오류는 한 곳에서 같은 규칙으로 바꾼다: 시간 초과·연결 실패는 503 UPSTREAM_TIMEOUT, 그 밖은 500 INTERNAL_ERROR.
    내부 메시지와 요청 내용(질문·원고)은 클라이언트와 로그에 남기지 않고 예외 종류와 스키마 이름만 기록한다.
    """
    chain = model.with_structured_output(schema, include_raw=True)
    try:
        out = chain.invoke(messages)
    except (openai.APITimeoutError, openai.APIConnectionError):
        raise ApiError(503, "UPSTREAM_TIMEOUT", "응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.")
    except Exception as e:
        logger.error("llm call failed: %s (%s)", type(e).__name__, schema.__name__)
        raise ApiError(500, "INTERNAL_ERROR", "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")

    parsed = out.get("parsed")
    if parsed is None:
        logger.error("llm structured output parse failed (%s)", schema.__name__)
        raise ApiError(500, "INTERNAL_ERROR", "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")
    usage = getattr(out.get("raw"), "usage_metadata", None) or {}
    return parsed, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


def generate_structured(system: str, user: str, schema: type[BaseModel]) -> tuple[BaseModel, int, int]:
    """임의의 Pydantic 스키마로 구조화 출력을 받는다(텍스트 전용). 반환: (schema 인스턴스, 입력 토큰, 출력 토큰).

    선행연구 표·주제 후보·원고 주장 같은 모드별 출력에 쓴다. 이미지가 필요한 답변 초안은 generate를 쓴다.
    """
    return _invoke(get_llm(), schema, [("system", system), ("human", user)])


def generate(system: str, user: str, images: list[tuple[str, str]] | None = None) -> tuple[AnswerDraft, int, int]:
    """구조화 출력으로 답변 초안을 받는다. 반환: (draft, 입력 토큰, 출력 토큰).

    images: [(근거 라벨, PNG base64)]. 있으면 사용자 메시지에 페이지 이미지를 함께 넣고 LLM_IMAGE_MODEL로 부른다.
    """
    model = get_llm(config_rag.LLM_IMAGE_MODEL, config_rag.LLM_IMAGE_REASONING_EFFORT) if images else get_llm()
    human: str | list = user
    if images:
        human = [{"type": "text", "text": user}]
        for label, b64 in images:
            human.append({"type": "text", "text": f"[{label}] 원본 페이지"})
            human.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}})
    return _invoke(model, AnswerDraft, [("system", system), ("human", human)])
