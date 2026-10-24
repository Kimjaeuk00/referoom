"""RAG 색인 저장소. 검색은 DEV_03 6절 store 계약(search/chunks_of_paper/index_version/readiness)과 같은 시그니처이고,
적재·삭제(add_paper/delete_paper)와 원본 PDF 경로(pdf_path)를 더한다.

- 팀마다 {LOCAL_INDEX_DIR}/{team_id}/ 에 vectors.npy·chunks.json·meta.json (pickle 없음)
- 점수는 코사인 유사도(높을수록 유사). 색인이 없으면 예외 대신 빈 리스트를 돌려준다
- 쓰기는 팀별 잠금 안에서 디스크의 최신 색인을 다시 읽어 합친다. 읽기 캐시는 meta.json이 바뀌면 다시 읽는다
  (여러 워커 프로세스가 같은 볼륨을 읽어도 최신 색인을 쓰도록)
- 동기 함수다. FastAPI에서는 스레드풀에서 호출한다 (임베딩이 느리다)
"""
import json
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.rag import config_rag
from app.rag.local_store import embedder, ingest
from app.rag.store_stub import Hit  # 계약상의 Hit 모델을 그대로 사용


class PaperExistsError(ValueError):
    """이미 색인된 paper_id. 다시 적재하려면 replace=True."""


@dataclass
class _Index:
    vectors: np.ndarray
    chunks: list[dict]
    meta: dict
    stamp: int  # meta.json 수정 시각 (ns)


_cache: dict[int, _Index | None] = {}
_lock = threading.Lock()                     # _cache 보호
_team_locks: dict[int, threading.Lock] = {}  # 팀별 쓰기 잠금


def _check_team(team_id: int) -> None:
    # 경로에 쓰이므로 JWT에서 온 양의 정수만 받는다
    if type(team_id) is not int or team_id <= 0:
        raise ValueError("유효한 team_id가 필요합니다.")


def _dir(team_id: int) -> Path:
    _check_team(team_id)
    return Path(config_rag.LOCAL_INDEX_DIR) / str(team_id)


def _team_lock(team_id: int) -> threading.Lock:
    with _lock:
        return _team_locks.setdefault(team_id, threading.Lock())


def _read(team_id: int) -> _Index | None:
    d = _dir(team_id)
    meta_path = d / "meta.json"
    if not meta_path.exists():
        return None
    stamp = meta_path.stat().st_mtime_ns
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    chunks = json.loads((d / "chunks.json").read_text(encoding="utf-8"))
    vectors = np.load(d / "vectors.npy")
    if not (len(chunks) == len(vectors) == meta.get("chunk_count")):
        raise RuntimeError(f"색인 파일이 서로 맞지 않습니다. 재색인이 필요합니다: {d}")
    return _Index(vectors=vectors, chunks=chunks, meta=meta, stamp=stamp)


def _load(team_id: int) -> _Index | None:
    meta_path = _dir(team_id) / "meta.json"
    stamp = meta_path.stat().st_mtime_ns if meta_path.exists() else None
    with _lock:
        cached = _cache.get(team_id)
        if team_id in _cache and (cached.stamp if cached else None) == stamp:
            return cached
    idx = _read(team_id)
    with _lock:
        _cache[team_id] = idx
    return idx


def reload(team_id: int | None = None) -> None:
    """캐시를 비운다 (team_id가 없으면 전체)."""
    with _lock:
        if team_id is None:
            _cache.clear()
        else:
            _cache.pop(team_id, None)


# ---- 검색 (계약) ----
def _rank(idx: _Index, query: str, k: int, keep) -> list[Hit]:
    if not len(idx.chunks):
        return []
    q = embedder.embed_query(query)
    scores = idx.vectors @ q
    order = np.argsort(-scores)
    hits: list[Hit] = []
    for i in order:
        c = idx.chunks[i]
        if keep(c["metadata"], float(scores[i])):
            hits.append(Hit(text=c["text"], score=float(scores[i]), metadata=c["metadata"]))
            if len(hits) >= k:
                break
    return hits


def search(team_id: int, sources: list[str], query: str, k: int = 5,
           paper_ids: list[int] | None = None, tags: list[str] | None = None,
           min_score: float | None = None) -> list[Hit]:
    idx = _load(team_id)
    # 이 저장소는 논문 본문(pdf)만 가진다
    if idx is None or "pdf" not in sources or k <= 0 or not query.strip():
        return []

    def keep(meta: dict, score: float) -> bool:
        if paper_ids and meta.get("paper_id") not in paper_ids:
            return False
        if tags and not set(tags) & set(str(meta.get("tags", "")).split(",")):
            return False
        return min_score is None or score >= min_score

    return _rank(idx, query, k, keep)


def chunks_of_paper(team_id: int, paper_id: int, query: str, k: int = 4) -> list[Hit]:
    idx = _load(team_id)
    if idx is None:
        return []
    return _rank(idx, query, k, lambda meta, _s: meta.get("paper_id") == paper_id)


def index_version(team_id: int) -> int:
    idx = _load(team_id)
    return int(idx.meta["index_version"]) if idx else 0


def readiness() -> dict:
    with _lock:
        return {"embedder": True, "stores_loaded": sum(1 for v in _cache.values() if v is not None)}


# ---- 적재·삭제 (RAG 소유) ----
def pdf_path(team_id: int, paper_id: int) -> Path | None:
    """보관한 원본 PDF. 다른 팀의 paper_id면 그 팀 폴더에 파일이 없으므로 None (팀 격리)."""
    _check_team(team_id)
    if type(paper_id) is not int or paper_id <= 0:
        return None
    path = Path(config_rag.PDF_DIR) / str(team_id) / f"{paper_id}.pdf"
    return path if path.is_file() else None


def team_meta(team_id: int) -> dict:
    idx = _load(team_id)
    return dict(idx.meta) if idx else {}


def add_paper(team_id: int, paper_id: int, pdf: Path | bytes, meta: dict, replace: bool = False) -> dict:
    """논문 한 편을 팀 색인에 더한다. 반환: {chunk_count, references, page_count, index_version}.

    meta: source(논문 제목, 필수)와 url·arxiv_id·year·tags·license 등 청크 공통 메타데이터.
    스캔 PDF 등은 ingest.IngestError, 이미 있으면 PaperExistsError (replace=True면 교체).
    """
    _check_team(team_id)
    if type(paper_id) is not int or paper_id <= 0:
        raise ValueError("유효한 paper_id가 필요합니다.")
    if not meta.get("source"):
        raise ValueError("청크 메타데이터에 source(논문 제목)가 필요합니다.")
    data = pdf.read_bytes() if isinstance(pdf, Path) else pdf

    # 느린 작업(추출·임베딩)은 잠금 밖에서 한다
    parsed = ingest.parse_pdf(data)
    base = {**meta, "team_id": team_id, "paper_id": paper_id, "type": "body"}
    chunks = ingest.paper_chunks(parsed, base)
    if not chunks:
        raise ingest.IngestError("색인할 본문이 없습니다.")
    vectors = embedder.embed_documents([c["text"] for c in chunks])

    with _team_lock(team_id):
        cur = _read(team_id)
        if cur is not None and cur.chunks:
            settings = ingest.index_settings()
            if any(cur.meta.get(k) != v for k, v in settings.items()) or cur.meta.get("dim") != vectors.shape[1]:
                raise RuntimeError("기존 색인과 임베딩·청킹 설정이 다릅니다. 팀 색인을 다시 만들어야 합니다.")
            exists = any(c["metadata"].get("paper_id") == paper_id for c in cur.chunks)
            if exists and not replace:
                raise PaperExistsError(f"이미 색인된 논문입니다: paper_id={paper_id}")
            keep = [i for i, c in enumerate(cur.chunks) if c["metadata"].get("paper_id") != paper_id]
            all_chunks = [cur.chunks[i] for i in keep] + chunks
            all_vectors = np.vstack([cur.vectors[keep], vectors]) if keep else vectors
        else:
            all_chunks, all_vectors = chunks, vectors
        _store_pdf(team_id, paper_id, data)
        saved = ingest.save_index(_dir(team_id), all_chunks, all_vectors, {"team_id": team_id})
        reload(team_id)
    return {"chunk_count": len(chunks), "references": parsed.references,
            "page_count": parsed.page_count, "index_version": saved["index_version"]}


def delete_paper(team_id: int, paper_id: int) -> int:
    """논문의 청크와 보관 PDF를 지운다. 반환: 지운 청크 수 (없으면 0)."""
    with _team_lock(team_id):
        cur = _read(team_id)
        removed = 0
        if cur is not None:
            keep = [i for i, c in enumerate(cur.chunks) if c["metadata"].get("paper_id") != paper_id]
            removed = len(cur.chunks) - len(keep)
            if removed:
                vectors = cur.vectors[keep] if keep else np.zeros((0, cur.vectors.shape[1]), dtype=np.float32)
                ingest.save_index(_dir(team_id), [cur.chunks[i] for i in keep], vectors, {"team_id": team_id})
        path = pdf_path(team_id, paper_id)
        if path:
            path.unlink()
        reload(team_id)
    return removed


def drop_team(team_id: int) -> None:
    """팀 색인을 비우고 보관 PDF를 지운다 (시드 재색인용).

    폴더를 지우지 않고 빈 색인을 써서 index_version이 계속 증가하게 한다 (응답 캐시 키가 되돌아가지 않도록).
    빈 색인에는 설정 검사를 하지 않으므로 설정을 바꾼 재색인도 된다.
    """
    with _team_lock(team_id):
        ingest.save_index(_dir(team_id), [], np.zeros((0, 0), dtype=np.float32), {"team_id": team_id})
        shutil.rmtree(Path(config_rag.PDF_DIR) / str(team_id), ignore_errors=True)
        reload(team_id)


def _store_pdf(team_id: int, paper_id: int, data: bytes) -> None:
    d = Path(config_rag.PDF_DIR) / str(team_id)
    d.mkdir(parents=True, exist_ok=True)
    ingest._write_atomic(d / f"{paper_id}.pdf", data)
