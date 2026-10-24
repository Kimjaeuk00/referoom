"""임베딩. 적재와 질의가 같은 모델·정규화를 쓰도록 이 모듈 한 곳만 사용한다.

EMBEDDING_BACKEND=openai(기본, EMBEDDING_MODEL=text-embedding-3-*) | local(sentence-transformers, 예: BAAI/bge-m3)
반환 벡터는 L2 정규화되어 내적 = 코사인 유사도(높을수록 유사).
"""
from functools import lru_cache

import numpy as np

from app.rag import config_rag


@lru_cache(maxsize=1)
def _model():
    if config_rag.EMBEDDING_BACKEND == "local":
        from sentence_transformers import SentenceTransformer  # 무거워서 local일 때만 import

        m = SentenceTransformer(config_rag.EMBEDDING_MODEL)
        m.max_seq_length = 512  # 청크(1000자)에 충분하고 메모리를 제한한다
        return m
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=config_rag.EMBEDDING_MODEL, api_key=config_rag.LLM_API_KEY)


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.clip(norms, 1e-12, None)


def _encode(texts: list[str]) -> np.ndarray:
    model = _model()
    if config_rag.EMBEDDING_BACKEND == "local":
        return np.asarray(model.encode(texts, batch_size=16, show_progress_bar=False), dtype=np.float32)
    return np.array(model.embed_documents(texts), dtype=np.float32)


def embed_documents(texts: list[str]) -> np.ndarray:
    return _normalize(_encode(texts))


def embed_query(text: str) -> np.ndarray:
    model = _model()
    if config_rag.EMBEDDING_BACKEND == "local":
        v = np.asarray(model.encode([text], show_progress_bar=False), dtype=np.float32)
    else:
        v = np.array([model.embed_query(text)], dtype=np.float32)
    return _normalize(v)[0]
