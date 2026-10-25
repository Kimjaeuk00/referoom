"""적재: PDF → 페이지별 텍스트 → 정리(머리말·참고문헌 제외) → 청크(본문+캡션) → 임베딩.

서비스 경로는 store.add_paper()가 이 모듈의 parse_pdf()·paper_chunks()를 쓴다.
아래 CLI는 시드 PDF 폴더로 팀 색인을 처음부터 다시 만든다 (개발·평가용).
실행: python -m app.rag.local_store.ingest [--team-id 3] [--seed-dir ...]
저장 형식({LOCAL_INDEX_DIR}/{team_id}/): vectors.npy, chunks.json, meta.json
청크 메타데이터는 DEV_03 4절 스키마를 따르고 kind·has_table·caption_label을 더한다.
"""
import argparse
import io
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.rag import config_rag
from app.rag.local_store import embedder
from app.rag.local_store.seed_papers import identify

logger = logging.getLogger("rag")

_MATH_CHARS = re.compile(r"[=∑∫∏√≈≤≥±×∂∇θλσμ]|\\frac|\$")  # 이전 규칙 (LAYOUT_RULES=off 비교용)
# 수식에만 나오는 기호. ±·×·%는 표에도 흔해서 뺐다. 그리스 문자는 본문 약어(μs 등)보다 수식에서 훨씬 많이 쓰인다
_MATH_STRONG = re.compile(r"[∑∫∏√∂∇≈≤≥∈∉⊂⊆∀∃→←↦⊙⊗∥∞∆\u0391-\u03a9\u03b1-\u03c9]|\\frac")
_NUM_TOKEN = re.compile(r"^[−\-+±×.,%()\d]+$")
# 캡션 시작: 줄 맨 앞의 "Figure 2." / "Fig. 3:" / "Table 1 |" / "그림 1." / "표 2:"
_CAPTION = re.compile(r"^\s*((?:Figure|Fig\.|Table|그림|표)\s*\d+)\s*[.:|]\s*\S", re.I)
# 앞 줄이 이 단어로 끝나면 본문 속 언급("shown in\nTable 1. ...")으로 보고 캡션에서 뺀다
_REF_TAIL = re.compile(r"\b(in|see|of|and|to|from|by|with|on|as|and|및|의)\s*$", re.I)


def clean_text(text: str) -> str:
    # PDF 추출 시 합자(ﬁ, ﬂ 등)가 한 글자로 나오므로 NFKC로 풀어준다 (preﬁx → prefix)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("-\n", "")  # 줄바꿈 하이픈 제거
    text = re.sub(r"\s+", " ", text).strip()
    if config_rag.LAYOUT_RULES:
        text = re.sub(r"(\d) \.(\d)", r"\1.\2", text)  # 표 숫자 쪼개짐 (92 .8 → 92.8)
    return text


def numeric_ratio(text: str) -> float:
    toks = text.split()
    return sum(bool(_NUM_TOKEN.match(t)) and any(c.isdigit() for c in t) for t in toks) / len(toks) if toks else 0.0


def has_table(text: str) -> bool:
    """숫자 토큰이 30% 이상이면 표·그래프 축에서 온 글자로 본다 (구조는 복구하지 못하므로 표시만 한다)."""
    return numeric_ratio(text) >= 0.3


def has_math(text: str) -> bool:
    """수식 청크 판단 (needs_review 판단용 휴리스틱).

    LAYOUT_RULES=on: 수식 전용 기호와 '='를 합쳐 3개 이상이고 표형 청크가 아닐 때.
    off: 이전 규칙(±·× 포함 기호 3개 이상) — 표 청크가 수식으로 오탐되던 문제가 있다.
    """
    if not config_rag.LAYOUT_RULES:
        return len(_MATH_CHARS.findall(text)) >= 3
    return len(_MATH_STRONG.findall(text)) + text.count("=") >= 3 and not has_table(text)


def read_raw_pages(pdf: Path | bytes) -> list[str]:
    """리더가 뽑은 페이지별 원문 (줄바꿈 유지). 경로 또는 PDF bytes."""
    if config_rag.PDF_READER == "pymupdf":
        import pymupdf  # AGPL 라이선스라 비교 실험에서만 쓴다

        doc = pymupdf.open(stream=pdf, filetype="pdf") if isinstance(pdf, bytes) else pymupdf.open(str(pdf))
        return [page.get_text("text") for page in doc]
    reader = PdfReader(io.BytesIO(pdf) if isinstance(pdf, bytes) else str(pdf))
    return [page.extract_text() or "" for page in reader.pages]


def _line_key(line: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line))).strip().lower()


def strip_repeated_lines(raw_pages: list[str], edge: int = 3, min_share: float = 0.4) -> list[str]:
    """여러 페이지의 위·아래 끝에 반복되는 줄(머리말·꼬리말·쪽번호)을 지운다.

    페이지 위·아래 edge줄만 보고, 숫자를 #로 바꾼 같은 줄이 전체 페이지의 min_share 이상(최소 3쪽)에 나오면 반복으로 본다.
    """
    def edges(lines):
        return lines[:edge] + lines[-edge:]

    split = [t.splitlines() for t in raw_pages]
    counts = {}
    for lines in split:
        for key in {_line_key(l) for l in edges(lines)}:
            if len(key) >= 3 or key == "#":  # "#"은 숫자만 있는 줄(쪽번호)
                counts[key] = counts.get(key, 0) + 1
    need = max(3, int(len(raw_pages) * min_share))
    repeated = {k for k, n in counts.items() if n >= need}
    out = []
    for lines in split:
        n = len(lines)
        out.append("\n".join(l for i, l in enumerate(lines)
                             if not ((i < edge or i >= n - edge) and _line_key(l) in repeated)))
    return out


def find_captions(raw_page: str, max_chars: int = 400) -> list[tuple[str, str]]:
    """페이지 원문에서 그림·표 캡션을 찾는다. 반환: [(라벨 'Figure 2', 캡션 문장)]."""
    lines = raw_page.splitlines()
    found = []
    for i, line in enumerate(lines):
        m = _CAPTION.match(line)
        if not m or (i > 0 and _REF_TAIL.search(lines[i - 1])):
            continue
        text = clean_text("\n".join(lines[i:i + 8]))[: max_chars + 100]
        end = max(text.rfind(". ", 0, max_chars), text.rfind(".", 0, max_chars) if len(text) <= max_chars else -1)
        text = text[: end + 1] if end > len(m.group(1)) + 5 else text[:max_chars]
        label = re.sub(r"\s+", " ", m.group(1)).replace("Fig.", "Figure").title()
        found.append((label, text.strip()))
    return found


_REF_HEADING = re.compile(r"^\s*(?:(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+)?(?:references|bibliography|참고\s*문헌)\s*[:：]?\s*$", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
REF_YEAR_DENSITY = 4.0  # 1000자당 연도 표기 수. 시드 9편: 참고문헌 쪽 4.1~8.3, 부록 쪽 0~3.6


def year_density(text: str) -> float:
    return len(_YEAR.findall(text)) * 1000 / max(1, len(text))


def strip_references(raw_pages: list[str]) -> tuple[list[str], tuple[int, int] | None]:
    """참고문헌 구간을 비운다. 반환: (페이지별 원문, 제외한 (시작쪽, 끝쪽) 또는 None).

    'References' 제목 줄부터 그 쪽 끝까지 지우고, 다음 쪽부터는 연도 밀도가 높은 쪽만 이어서 지운다.
    밀도가 낮은 첫 쪽(보통 부록)에서 멈추므로 참고문헌 뒤의 부록 표·그림은 남는다.
    1쪽의 제목은 보지 않는다 (목차·제목에 'References'가 단독으로 오는 경우를 피하려고).
    """
    pages = list(raw_pages)
    for p in range(1, len(pages)):
        lines = pages[p].splitlines()
        hit = next((i for i, l in enumerate(lines) if _REF_HEADING.match(l)), None)
        if hit is None:
            continue
        pages[p] = "\n".join(lines[:hit])
        end = p
        while end + 1 < len(pages) and year_density(pages[end + 1]) >= REF_YEAR_DENSITY:
            end += 1
            pages[end] = ""
        return pages, (p + 1, end + 1)
    return pages, None


class IngestError(ValueError):
    """적재할 수 없는 PDF (스캔본 등). 메시지는 사용자에게 보여 줄 수 있는 문장이다."""


@dataclass
class ParsedPaper:
    pages: list[tuple[int, str]]   # 정리된 본문 (쪽 번호는 1부터, 빈 쪽 제외)
    raw: list[str]                 # 머리말·참고문헌을 지운 원문 (캡션 찾기용, 줄바꿈 유지)
    references: tuple[int, int] | None
    page_count: int


def parse_pdf(pdf: Path | bytes) -> ParsedPaper:
    raw = read_raw_pages(pdf)
    if not raw or sum(len(re.sub(r"\s", "", t)) for t in raw) / len(raw) < 50:
        raise IngestError("텍스트 추출 불가(스캔 PDF)")
    references = None
    if config_rag.LAYOUT_RULES:
        raw = strip_repeated_lines(raw)
        raw, references = strip_references(raw)
    pages = [(i, t) for i, t in enumerate((clean_text(r) for r in raw), start=1) if t]
    return ParsedPaper(pages=pages, raw=raw, references=references, page_count=len(raw))


def paper_chunks(parsed: ParsedPaper, base_meta: dict) -> list[dict]:
    """본문 청크 + 캡션 청크. base_meta에는 team_id·paper_id·source가 있어야 한다."""
    body = chunk_pages(parsed.pages, base_meta)
    if not config_rag.LAYOUT_RULES:
        return body
    return body + captions_from_raw(parsed.raw, base_meta, start=len(body))


def read_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """페이지별 정리된 텍스트. 페이지 번호는 1부터, 빈 페이지는 제외."""
    raw = read_raw_pages(pdf_path)
    if config_rag.LAYOUT_RULES:
        raw = strip_repeated_lines(raw)
    pages = []
    for i, text in enumerate(raw, start=1):
        text = clean_text(text)
        if text:
            pages.append((i, text))
    return pages


def caption_chunks(pdf_path: Path, base_meta: dict, start: int) -> list[dict]:
    return captions_from_raw(strip_repeated_lines(read_raw_pages(pdf_path)), base_meta, start)


def captions_from_raw(raw: list[str], base_meta: dict, start: int) -> list[dict]:
    """그림·표 캡션을 별도 청크로 만든다. 캡션은 그림 내용을 요약한 문장이라 그림 페이지를 찾는 검색 단서가 된다.
    같은 라벨은 논문에서 처음 나온 것만 쓴다 (본문 속 언급이 캡션으로 잡히는 경우를 줄이기 위해)."""
    chunks, seen = [], set()
    for page_no, text in enumerate(raw, start=1):
        for label, caption in find_captions(text):
            if label in seen or len(caption) < 20:
                continue
            seen.add(label)
            kind = "table" if label.lower().startswith(("table", "표")) else "figure"
            chunks.append({
                "text": caption,
                "metadata": {**base_meta, "page": page_no, "has_math": False, "has_table": kind == "table",
                             "kind": "caption", "caption_label": label, "caption_of": kind,
                             "chunk_id": f"{base_meta['paper_id']}:caption:{start + len(chunks)}"},
            })
    return chunks


def chunk_pages(pages: list[tuple[int, str]], base_meta: dict,
                chunk_size: int | None = None, chunk_overlap: int | None = None) -> list[dict]:
    """페이지를 넘지 않게 분할한다 (page 메타데이터 유지)."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size or config_rag.CHUNK_SIZE,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else config_rag.CHUNK_OVERLAP,
    )
    chunks = []
    for page_no, text in pages:
        for piece in splitter.split_text(text):
            chunks.append({
                "text": piece,
                "metadata": {**base_meta, "page": page_no, "has_math": has_math(piece),
                             "has_table": has_table(piece), "kind": "text",
                             "chunk_id": f"{base_meta['paper_id']}:body:{len(chunks)}"},
            })
    return chunks


def seed_meta(pdf: Path) -> dict | None:
    """시드 파일명에서 청크 공통 메타데이터. 목록에 없는 파일이면 None."""
    info = identify(pdf.name)
    if info is None:
        return None
    return {"paper_id": info["paper_id"], "source": info["title"], "authors": info.get("authors", ""),
            "arxiv_id": info["arxiv_id"],
            "version": info["version"], "year": info["year"], "tags": info.get("tags", "peft"),
            "url": info["url"], "license": "unknown"}


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save_index(index_dir: Path, chunks: list[dict], vectors: np.ndarray, extra_meta: dict) -> dict:
    """색인 파일 3개를 쓴다. 파일마다 임시 파일 → 교체로 쓰고 meta.json을 마지막에 써서,
    중간에 멈추면 읽는 쪽이 개수 불일치로 알아챈다 (store._load)."""
    index_dir.mkdir(parents=True, exist_ok=True)
    meta_path = index_dir / "meta.json"
    prev = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta = {
        **extra_meta,
        "index_version": int(prev.get("index_version", 0)) + 1,  # 쓸 때마다 증가 (캐시 무효화용)
        **index_settings(),
        "dim": int(vectors.shape[1]) if len(vectors) else prev.get("dim", 0),
        "chunk_count": len(chunks),
    }
    buf = io.BytesIO()
    np.save(buf, vectors.astype(np.float32))
    _write_atomic(index_dir / "vectors.npy", buf.getvalue())
    _write_atomic(index_dir / "chunks.json", json.dumps(chunks, ensure_ascii=False).encode("utf-8"))
    _write_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8"))
    return meta


def index_settings() -> dict:
    """색인과 질의가 같아야 하는 설정. 기존 색인과 다르면 섞어 쓰지 않는다 (store.add_paper)."""
    return {
        "embedding_backend": config_rag.EMBEDDING_BACKEND,
        "embedding_model": config_rag.EMBEDDING_MODEL,
        "chunk_size": config_rag.CHUNK_SIZE,
        "chunk_overlap": config_rag.CHUNK_OVERLAP,
        "pdf_reader": config_rag.PDF_READER,
        "layout_rules": config_rag.LAYOUT_RULES,
    }


def build_index(team_id: int, seed_dir: Path | None = None) -> dict:
    """시드 폴더의 PDF로 팀 색인을 처음부터 다시 만든다 (기존 색인·보관 PDF는 지운다)."""
    from app.rag.local_store import store

    seed_dir = seed_dir or config_rag.SEED_DIR
    store.drop_team(team_id)
    papers = []
    for pdf in sorted(seed_dir.glob("*.pdf")):
        meta = seed_meta(pdf)
        if meta is None:
            logger.warning("skip unknown pdf: %s", pdf.name)
            continue
        store.add_paper(team_id, meta.pop("paper_id"), pdf, meta)
        papers.append(meta["arxiv_id"])
    if not papers:
        raise SystemExit(f"색인할 PDF가 없습니다: {seed_dir}")
    return {**store.team_meta(team_id), "papers": papers}


def main() -> None:
    ap = argparse.ArgumentParser(description="로컬 테스트 색인 생성")
    ap.add_argument("--team-id", type=int, default=config_rag.LOCAL_TEAM_ID)
    ap.add_argument("--seed-dir", type=Path, default=config_rag.SEED_DIR)
    args = ap.parse_args()
    meta = build_index(args.team_id, args.seed_dir)
    sys.stdout.write(
        f"indexed papers={len(meta['papers'])} chunks={meta['chunk_count']} dim={meta['dim']} "
        f"version={meta['index_version']} model={meta['embedding_model']}\n"
    )


if __name__ == "__main__":
    main()
