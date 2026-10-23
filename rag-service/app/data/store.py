"""팀별 FAISS 저장소 초안. 단일 프로세스·단일 이벤트 루프를 전제로 합니다.

앱 시작 시 initialize_store()에 실제 임베더를 전달합니다. 동기 검색 함수는
FastAPI의 스레드풀에서 호출해야 합니다. JWT·DB 트랜잭션은 호출 측 책임입니다.
"""

import asyncio
import json
import math
import os
from pathlib import Path
from threading import RLock

import faiss
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from pydantic import BaseModel


class Hit(BaseModel):
    text: str
    score: float
    metadata: dict


SOURCES = ("pdf", "web", "annotation")
_root = Path(__file__).resolve().parents[2] / "faiss_db"
_embeddings: Embeddings | None = None
_settings: dict = {}
_stores: dict[tuple[int, str], FAISS] = {}
_write_locks: dict[tuple[int, str], asyncio.Lock] = {}
_guard = RLock()


class _NormalizedEmbeddings(Embeddings):
    """본문과 질문 벡터를 모두 정규화하여 내적을 코사인 유사도로 맞춥니다."""

    def __init__(self, delegate: Embeddings, dim: int):
        self.delegate = delegate
        self.dim = dim

    def _normalize(self, vector: list[float]) -> list[float]:
        if not vector or len(vector) != self.dim or not all(math.isfinite(x) for x in vector):
            raise ValueError("임베딩 벡터의 차원 또는 값이 올바르지 않습니다.")
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0:
            raise ValueError("영벡터는 검색에 사용할 수 없습니다.")
        return [x / norm for x in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._normalize(vector) for vector in self.delegate.embed_documents(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self._normalize(self.delegate.embed_query(text))


def initialize_store(
    embedder: Embeddings,
    *,
    embedding_backend: str = "local",
    model: str = "BAAI/bge-m3",
    chunk_size: int = 500,
    faiss_dir: str | Path | None = None,
) -> None:
    """앱 시작 시 1회 호출합니다. 임베더 선택·생성은 embedder.py에서 수행합니다."""
    global _embeddings, _root, _settings
    with _guard:
        if _embeddings is not None:
            raise RuntimeError("저장소가 이미 초기화되었습니다. 설정 변경 시 앱을 재시작하세요.")
        if embedding_backend not in {"local", "openai"} or chunk_size <= 0 or not model:
            raise ValueError("임베딩 백엔드·모델·청크 크기 설정을 확인하세요.")
        vector = embedder.embed_query("warmup")
        normalized = _NormalizedEmbeddings(embedder, len(vector))
        normalized._normalize(vector)
        _root = Path(faiss_dir or os.getenv("FAISS_DIR") or _root).resolve()
        _settings = {
            "embedding_backend": embedding_backend,
            "model": model,
            "dim": len(vector),
            "chunk_size": chunk_size,
            "metric": "cosine",
        }
        _embeddings = normalized


def _path(team_id: int, source: str) -> Path:
    # team_id는 호출 측에서 검증한 JWT 값만 전달해야 합니다.
    if type(team_id) is not int or team_id <= 0 or source not in SOURCES:
        raise ValueError("유효한 team_id와 저장소 이름이 필요합니다.")
    return _root / str(team_id) / source


def _read_meta(path: Path) -> dict:
    return json.loads((path / "index_meta.json").read_text(encoding="utf-8"))


def _load(team_id: int, source: str) -> FAISS | None:
    """_guard 안에서 호출합니다. 없으면 None, 불완전·비호환 인덱스는 오류입니다."""
    path = _path(team_id, source)
    key = (team_id, source)
    if key in _stores:
        return _stores[key]
    files = [path / name for name in ("index.faiss", "index.pkl", "index_meta.json")]
    if not any(file.exists() for file in files):
        return None
    if not all(file.is_file() for file in files):
        raise RuntimeError(f"불완전한 인덱스입니다. 재색인이 필요합니다: {path}")
    if _embeddings is None:
        raise RuntimeError("initialize_store()로 임베더를 먼저 준비하세요.")
    meta = _read_meta(path)
    if any(meta.get(key) != value for key, value in _settings.items()):
        raise RuntimeError(f"설정과 호환되지 않는 인덱스입니다. 재색인이 필요합니다: {path}")
    # 서버가 직접 생성하고 쓰기 권한을 제한한 디렉터리만 사용해야 합니다.
    store = FAISS.load_local(
        str(path), _embeddings,
        allow_dangerous_deserialization=True,
        distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
    )
    if store.index.d != _settings["dim"] or store.index.metric_type != faiss.METRIC_INNER_PRODUCT:
        raise RuntimeError("인덱스 차원·거리 방식이 다릅니다. 재색인이 필요합니다.")
    _stores[key] = store
    return store


def index_version(team_id: int) -> int:
    """각 저장소에 기록한 팀 공통 증가 번호의 최댓값을 반환합니다."""
    with _guard:
        versions = []
        for source in SOURCES:
            path = _path(team_id, source)
            if (path / "index_meta.json").is_file():
                versions.append(int(_read_meta(path)["index_version"]))
            elif any((path / name).exists() for name in ("index.faiss", "index.pkl")):
                raise RuntimeError(f"인덱스 버전 정보가 없습니다. 재색인이 필요합니다: {path}")
        return max(versions, default=0)


def _persist(team_id: int, source: str, store: FAISS) -> None:
    version = index_version(team_id) + 1
    path = _path(team_id, source)
    path.mkdir(parents=True, exist_ok=True)
    store.save_local(str(path))
    meta = {**_settings, "index_version": version}
    temporary = path / "index_meta.json.tmp"
    temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path / "index_meta.json")


async def add_documents(team_id: int, source: str, docs: list[Document]) -> list[str]:
    """청커의 Document.id로 증분 추가합니다. 중복 ID는 덮어쓰지 않습니다."""
    _path(team_id, source)
    lock = _write_locks.setdefault((team_id, source), asyncio.Lock())
    async with lock:
        return await asyncio.to_thread(_add_documents, team_id, source, docs)


def _add_documents(team_id: int, source: str, docs: list[Document]) -> list[str]:
    with _guard:
        if _embeddings is None:
            raise RuntimeError("initialize_store()로 임베더를 먼저 준비하세요.")
        if not docs:
            return []
        expected_type = {"pdf": "body", "web": "web", "annotation": "annotation"}[source]
        for doc in docs:
            if doc.metadata.get("team_id") != team_id or doc.metadata.get("type") != expected_type:
                raise ValueError("청크의 팀 또는 type이 대상 저장소와 다릅니다.")
            paper_id = doc.metadata.get("paper_id")
            if type(paper_id) is not int or paper_id <= 0:
                raise ValueError("청크에 유효한 paper_id가 필요합니다.")
            prefix = f"{paper_id}:{expected_type}:"
            if not doc.id or not doc.id.startswith(prefix) or not doc.id[len(prefix):].isdigit():
                raise ValueError("청크 ID는 {paper_id}:{type}:{순번} 형식이어야 합니다.")
        ids = [doc.id for doc in docs]
        if len(set(ids)) != len(ids):
            raise ValueError("추가할 청크 ID가 중복됩니다.")
        store = _load(team_id, source)
        if store is None:
            store = FAISS(
                embedding_function=_embeddings,
                index=faiss.IndexFlatIP(_settings["dim"]),
                docstore=InMemoryDocstore(),
                index_to_docstore_id={},
                distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT,
            )
        if set(ids) & set(store.index_to_docstore_id.values()):
            raise ValueError("이미 색인된 청크 ID입니다. 재색인 전 기존 청크를 삭제하세요.")
        try:
            store.add_documents(docs, ids=ids)
            _persist(team_id, source, store)
        except Exception:
            _stores.pop((team_id, source), None)
            raise
        _stores[(team_id, source)] = store
        return ids


def search(
    team_id: int,
    sources: list[str],
    query: str,
    k: int = 5,
    paper_ids: list[int] | None = None,
    tags: list[str] | None = None,
    min_score: float | None = None,
) -> list[Hit]:
    """점수는 원래 코사인 유사도(-1~1)입니다. 높을수록 유사합니다.

    tags가 여러 개면 하나 이상 일치하는 OR 필터를 적용합니다(팀 확인 필요).
    """
    for source in sources:
        _path(team_id, source)
    _path(team_id, "pdf")
    if k <= 0 or not query.strip() or paper_ids == []:
        return []

    def matches(metadata: dict) -> bool:
        if metadata.get("team_id") != team_id:
            return False
        if paper_ids is not None and metadata.get("paper_id") not in paper_ids:
            return False
        stored_tags = metadata.get("tags") or []
        if isinstance(stored_tags, str):
            stored_tags = [tag.strip() for tag in stored_tags.split(",") if tag.strip()]
        return not tags or bool(set(tags) & set(stored_tags))

    with _guard:
        stores = [store for source in dict.fromkeys(sources) if (store := _load(team_id, source)) is not None]
        if not stores:
            return []
        vector = _embeddings.embed_query(query)
        hits = []
        for store in stores:
            # FAISS는 검색 후 필터링하므로 모든 벡터를 후보로 조회합니다.
            results = store.similarity_search_with_score_by_vector(
                vector, k=k, filter=matches, fetch_k=max(k, store.index.ntotal),
            )
            for doc, score in results:
                score = max(-1.0, min(1.0, float(score)))
                if min_score is None or score >= min_score:
                    hits.append(Hit(text=doc.page_content, score=score, metadata=dict(doc.metadata)))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:k]


def chunks_of_paper(team_id: int, paper_id: int, query: str, k: int = 4) -> list[Hit]:
    return search(team_id, list(SOURCES), query, k=k, paper_ids=[paper_id])


async def delete_documents(
    team_id: int, source: str, *, paper_id: int | None = None, batch_id: int | None = None,
) -> int:
    """논문 삭제·배치 롤백용. DB 행 삭제는 호출 측에서 수행합니다."""
    _path(team_id, source)
    if (paper_id is None) == (batch_id is None):
        raise ValueError("paper_id 또는 batch_id 중 하나를 지정하세요.")
    lock = _write_locks.setdefault((team_id, source), asyncio.Lock())
    async with lock:
        return await asyncio.to_thread(_delete_documents, team_id, source, paper_id, batch_id)


def _delete_documents(team_id: int, source: str, paper_id: int | None, batch_id: int | None) -> int:
    with _guard:
        store = _load(team_id, source)
        if store is None:
            return 0
        key, value = ("paper_id", paper_id) if paper_id is not None else ("batch_id", batch_id)
        ids = [
            doc_id for doc_id in store.index_to_docstore_id.values()
            if isinstance(doc := store.docstore.search(doc_id), Document)
            and doc.metadata.get("team_id") == team_id and doc.metadata.get(key) == value
        ]
        if ids:
            try:
                store.delete(ids=ids)
                _persist(team_id, source, store)
            except Exception:
                _stores.pop((team_id, source), None)
                raise
        return len(ids)


def get_paper(team_id: int, paper_id: int) -> dict | None:
    _path(team_id, "pdf")
    raise NotImplementedError("repo.py의 비동기 DB 접근과 동기 검색 계약의 연결 방식을 먼저 합의해야 합니다.")


def readiness() -> dict:
    return {"embedder": _embeddings is not None, "stores_loaded": len(_stores)}
