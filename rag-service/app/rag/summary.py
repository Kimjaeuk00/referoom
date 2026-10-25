"""논문 요약 (POST /summary): 논문 한 편을 문제·핵심 아이디어·방법·결과·한계·(관점별) 체크 섹션으로 요약한다.

흐름
  1. 논문이 이 팀 색인에 없으면 404 NOT_FOUND (다른 팀 논문도 같은 404라서 존재 여부가 드러나지 않는다)
  2. 섹션마다 다른 질의로 그 논문의 청크를 모아 [S#] 블록으로 만들고, 구조화 호출 1회로 6개 섹션을 채운다
  3. 섹션 본문의 근거 라벨이 이 논문 블록에 없거나 비어 있으면 그 섹션은 "논문에서 찾을 수 없음"으로 둔다(근거 없는 문장은 내보내지 않는다)
  4. 응답의 sources는 프론트가 읽는 '제목 p.N' 문자열이고, 본문에는 [S#] 표시를 남기지 않는다
섹션은 항상 6개가 순서대로 나온다. 마지막 check 섹션만 관점에 따라 제목과 내용이 다르다(dev=구현 시 체크포인트, rnd=선행연구 비교·재현성).
TODO(측정 후): 같은 논문·관점의 요약은 반복해서 요청된다. 비용이 문제로 확인되면 색인 버전(store.index_version)을 키로 캐시한다.
"""
import logging
import re
import time

from app.rag import config_rag, llm
from app.rag.context import LABEL_RE, Block, build_blocks, render_context, source_strings
from app.rag.deps import CurrentUser, store
from app.rag.errors import ApiError
from app.rag.pipeline import needs_review
from app.rag.prompts import SUMMARY_CHECK, SUMMARY_EMPTY_TEXT, SUMMARY_PROMPT, SUMMARY_SECTIONS, SUMMARY_USER, VIEW_RULES
from app.rag.schemas import SummaryDraft, SummaryRequest, SummaryResponse, SummarySection

logger = logging.getLogger("rag")

_INLINE_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _sections(view: str) -> list[tuple[str, str, str, str]]:
    """(key, 제목, 설명, 검색 질의) 6개. 마지막 check 섹션은 관점에 따라 다르다."""
    return [*SUMMARY_SECTIONS, SUMMARY_CHECK[view]]


def _evidence(team_id: int, paper_id: int, sections: list[tuple[str, str, str, str]]) -> list:
    chosen, seen = [], set()
    for _, _, _, query in sections:
        for h in store.chunks_of_paper(team_id, paper_id, query, k=config_rag.SUMMARY_CHUNKS_PER_SECTION):
            key = (h.metadata.get("page"), h.text[:80])
            if key not in seen:
                seen.add(key)
                chosen.append(h)
    return sorted(chosen, key=lambda h: h.metadata.get("page") or 0)


def _body(text: str | None) -> str | None:
    """본문 정리: [S#] 표시 제거, 줄 안의 공백 정리(줄바꿈은 마크다운 목록을 위해 유지), 길이 상한. 비면 None."""
    if not text:
        return None
    cleaned = LABEL_RE.sub("", text)
    cleaned = "\n".join(_INLINE_SPACE_RE.sub(" ", line).strip() for line in cleaned.splitlines())
    cleaned = _BLANK_LINES_RE.sub("\n\n", cleaned).strip()
    return cleaned[: config_rag.SUMMARY_TEXT_MAX_CHARS] or None


def run(req: SummaryRequest, user: CurrentUser, usage: dict | None = None) -> SummaryResponse:
    started = time.monotonic()
    view = req.view or user.view or "dev"
    if req.paper_id not in store.paper_chunk_counts(user.team_id):
        raise ApiError(404, "NOT_FOUND", "논문을 찾을 수 없습니다.")

    sections = _sections(view)
    hits = _evidence(user.team_id, req.paper_id, sections)
    if not hits:
        raise ApiError(404, "NOT_FOUND", "논문을 찾을 수 없습니다.")  # 색인에 있는데 청크를 못 읽는 경우도 '없음'으로 둔다
    blocks = build_blocks(hits, max_chars=config_rag.SUMMARY_CONTEXT_CHARS)
    local = {b.label: b for b in blocks}

    guide = "\n".join(f"- {key} ({title}): {desc}" for key, title, desc, _ in sections)
    system = SUMMARY_PROMPT.format(sections=guide, view_rules=VIEW_RULES[view])
    draft, in_tok, out_tok = llm.generate_structured(system, SUMMARY_USER.format(context=render_context(blocks), title=blocks[0].title), SummaryDraft)
    by_key = {s.key: s for s in draft.sections}  # 같은 key가 여러 번 오면 마지막 것

    out: list[SummarySection] = []
    used: list[Block] = []
    for key, title, _, _ in sections:
        item = by_key.get(key)
        text = _body(item.text) if item else None
        cited = [local[label] for label in dict.fromkeys(item.labels) if label in local] if item else []  # 이 논문 블록에 있는 라벨만
        if text and cited:
            out.append(SummarySection(key=key, title=title, text=text, sources=source_strings(cited)))
            used.extend(b for b in cited if b not in used)
        else:  # 근거 라벨이 없거나 이 논문 블록에 없는 본문은 내보내지 않는다
            out.append(SummarySection(key=key, title=title, text=SUMMARY_EMPTY_TEXT, sources=[]))

    resp = SummaryResponse(
        paper_id=req.paper_id, title=blocks[0].title, view=view, sections=out,
        needs_review=needs_review(" ".join(s.text for s in out if s.sources), used, False, 1.0), latency_ms=0,
    )
    if usage is not None:
        usage["in_tok"], usage["out_tok"] = in_tok, out_tok
    resp.latency_ms = int((time.monotonic() - started) * 1000)
    # 논문 본문·요약은 로그에 남기지 않는다 (건수·토큰·지연만)
    logger.info(
        "rag-summary sections=%d supported=%d in_tok=%d out_tok=%d latency_ms=%d",
        len(out), sum(1 for s in out if s.sources), in_tok, out_tok, resp.latency_ms,
    )
    return resp
