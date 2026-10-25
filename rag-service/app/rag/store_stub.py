"""검색 인터페이스 스텁. TODO(data): 데이터 파트 store.py가 완성되면 deps.py의 import만 교체한다.

시그니처는 DEV_03 6절 계약과 동일하다. 점수는 높을수록 유사.
"""
from pydantic import BaseModel


class Hit(BaseModel):
    text: str
    score: float
    metadata: dict


_DUMMY = Hit(
    text="LoRA freezes the pre-trained model weights and injects trainable rank decomposition matrices.",
    score=0.82,
    metadata={
        "paper_id": 41,
        "source": "LoRA: Low-Rank Adaptation of Large Language Models",  # 논문 제목 (DEV_03 4절)
        "page": 1,
        "url": "https://arxiv.org/abs/2106.09685",
        "type": "body",
        "has_math": False,
    },
)


def search(team_id: int, sources: list[str], query: str, k: int = 5,
           paper_ids: list[int] | None = None, tags: list[str] | None = None,
           min_score: float | None = None) -> list[Hit]:
    return [_DUMMY][:k]


def chunks_of_paper(team_id: int, paper_id: int, query: str, k: int = 4) -> list[Hit]:
    return [_DUMMY][:k]


def index_version(team_id: int) -> int:
    return 0


def readiness() -> dict:
    return {"embedder": True, "stores_loaded": 0}
