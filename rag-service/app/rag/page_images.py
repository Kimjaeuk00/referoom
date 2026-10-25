"""질문 시 페이지 이미지 투입 (실험, PAGE_IMAGES=on).

표·그림·수식 표시가 붙은 근거 블록의 원본 PDF 페이지를 PNG로 렌더링한다. 렌더링은 pypdfium2(BSD-3/Apache-2.0).
원본 PDF 위치: 저장소가 pdf_path(team_id, paper_id)를 제공하면 그것을 쓰고(데이터 파트에 요청한 계약),
없으면 로컬 시드 폴더에서 찾는다(로컬 개발용). 팀 격리는 저장소 쪽 pdf_path가 책임진다.
"""
import base64
import io
import logging
from functools import lru_cache
from pathlib import Path

from app.rag import config_rag
from app.rag.context import Block

logger = logging.getLogger("rag")


@lru_cache(maxsize=1)
def _pdf_paths() -> dict[int, Path]:
    from app.rag.local_store.seed_papers import identify

    paths = {}
    for pdf in Path(config_rag.SEED_DIR).glob("*.pdf"):
        info = identify(pdf.name)
        if info:
            paths[info["paper_id"]] = pdf
    return paths


def _pdf_path(team_id: int, paper_id: int) -> Path | None:
    from app.rag.deps import store

    if hasattr(store, "pdf_path"):
        return store.pdf_path(team_id, paper_id)
    return _pdf_paths().get(paper_id)


@lru_cache(maxsize=64)
def render_page(team_id: int, paper_id: int, page: int) -> str | None:
    """페이지를 PNG base64로. 원본을 못 찾거나 렌더링에 실패하면 None (이미지 없이 텍스트로 답한다)."""
    path = _pdf_path(team_id, paper_id)
    if path is None:
        return None
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(path))
        img = pdf[page - 1].render(scale=config_rag.PAGE_IMAGE_SCALE).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning("page render failed: %s", type(e).__name__)
        return None


def pick_pages(team_id: int, blocks: list[Block], max_pages: int | None = None) -> list[tuple[str, str]]:
    """표시(visual)가 붙은 블록 중 점수가 높은 순으로 최대 max_pages 페이지. 반환: [(라벨, PNG base64)]."""
    max_pages = config_rag.PAGE_IMAGE_MAX if max_pages is None else max_pages
    out, seen = [], set()
    for b in sorted((b for b in blocks if b.visual and b.paper_id and b.page), key=lambda b: -b.score):
        if len(out) >= max_pages or (b.paper_id, b.page) in seen:
            continue
        seen.add((b.paper_id, b.page))
        img = render_page(team_id, b.paper_id, b.page)
        if img:
            out.append((b.label, img))
    return out
