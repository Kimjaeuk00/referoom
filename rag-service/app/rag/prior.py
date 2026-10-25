"""선행연구 모드 (/rag-query mode=prior): 선택한 논문들의 정리표와 비교 문단.

흐름
  1. 대상 논문 정하기: scope가 논문 목록이면 그 중 이 팀 색인에 있는 것만, 아니면 질문과 가까운 논문 상위 몇 편
  2. 논문마다 근거 모으기: 칸마다 다른 질의로 청크를 모아 [S#] 블록으로 만든다 (추출 질의는 prompts.PRIOR_EVIDENCE_QUERIES)
  3. 논문마다 구조화 추출 1회 (병렬): 6칸의 값과 근거 라벨. 근거 라벨이 없거나 없는 라벨이면 그 칸은 null로 버린다
  4. 쓰인 블록에 전역 라벨(S1..)을 다시 붙이고 표를 만든다
  5. 표만 보고 질문에 맞춘 비교 문단을 1회 생성하고 인용을 검증한다
근거가 하나도 없으면 LLM을 부르지 않고 handoff로 답한다. 질문·답변 원문은 로그에 남기지 않는다.
"""
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from app.rag import config_rag, llm
from app.rag.context import LABEL_RE, Block, build_blocks, details_of, render_context, source_strings, verify_citations
from app.rag.deps import CurrentUser, store
from app.rag.errors import ApiError
from app.rag.pipeline import SOURCE_MAP, _not_found
from app.rag.prompts import (
    LEVEL_RULES, PRIOR_COLUMN_NAMES, PRIOR_COMPARE_PROMPT, PRIOR_COMPARE_USER, PRIOR_EVIDENCE_QUERIES, PRIOR_EXTRACT_PROMPT,
    PRIOR_EXTRACT_USER, VIEW_RULES,
)
from app.rag.schemas import AnswerDraft, PriorRowDraft, RagRequest, RagResponse

logger = logging.getLogger("rag")

COLUMNS = tuple(PRIOR_COLUMN_NAMES)  # problem, method, dataset, metric, result, limitation
_DIGIT_RE = re.compile(r"\d")
_SPACE_RE = re.compile(r"\s+")


def _paper_ids(req: RagRequest, team_id: int) -> list[int]:
    """대상 논문 id. 팀 색인에 없는 id(다른 팀의 논문 포함)는 말없이 뺀다."""
    if "pdf" not in SOURCE_MAP[req.source]:
        return []  # 이 저장소는 논문 본문(pdf)만 가진다
    limit = config_rag.PRIOR_MAX_PAPERS
    if req.scope.type == "paper" and req.scope.ids:
        indexed = store.paper_chunk_counts(team_id)
        return [pid for pid in dict.fromkeys(req.scope.ids) if pid in indexed][:limit]
    hits = store.search(
        team_id, SOURCE_MAP[req.source], req.question, k=limit * 4,
        tags=req.scope.tags if req.scope.type == "tag" else None, min_score=config_rag.MIN_SCORE,
    )
    ids: list[int] = []
    for h in hits:
        pid = h.metadata.get("paper_id")
        if pid is not None and pid not in ids:
            ids.append(pid)
        if len(ids) >= limit:
            break
    return ids


def _evidence(team_id: int, paper_id: int) -> list:
    """한 논문의 근거 청크. 질의마다 상위 청크를 번갈아 모으고 중복은 뺀 뒤 쪽 순서로 놓는다."""
    per_query = [store.chunks_of_paper(team_id, paper_id, q, k=config_rag.PRIOR_CHUNKS_PER_PAPER) for q in PRIOR_EVIDENCE_QUERIES]
    chosen, seen = [], set()
    for rank in range(config_rag.PRIOR_CHUNKS_PER_PAPER):
        for hits in per_query:
            if rank < len(hits):
                h = hits[rank]
                key = (h.metadata.get("page"), h.text[:80])
                if key not in seen and len(chosen) < config_rag.PRIOR_CHUNKS_PER_PAPER:
                    seen.add(key)
                    chosen.append(h)
    return sorted(chosen, key=lambda h: h.metadata.get("page") or 0)


def _extract(blocks: list[Block]) -> tuple[PriorRowDraft, int, int]:
    user_msg = PRIOR_EXTRACT_USER.format(context=render_context(blocks), title=blocks[0].title)
    return llm.generate_structured(PRIOR_EXTRACT_PROMPT, user_msg, PriorRowDraft)


def _extract_safe(blocks: list[Block]):
    """한 논문이 실패해도 나머지는 계속한다. 반환: (draft 또는 None, 입력 토큰, 출력 토큰, 오류 또는 None)."""
    try:
        draft, i, o = _extract(blocks)
        return draft, i, o, None
    except ApiError as e:
        return None, 0, 0, e
    except Exception as e:  # 예상하지 못한 오류도 해당 논문만 건너뛴다. 내용은 남기지 않고 종류만 기록
        logger.error("prior extract failed: %s", type(e).__name__)
        return None, 0, 0, ApiError(500, "INTERNAL_ERROR", "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")


def _clean(value: str | None) -> str | None:
    """표 칸 문자열 정리: 공백 정리, 값 안의 [S#] 표시 제거(근거는 labels로만 잇는다), 길이 상한."""
    if not value:
        return None
    text = _SPACE_RE.sub(" ", LABEL_RE.sub("", value)).strip()
    if not text:
        return None
    return text[: config_rag.PRIOR_CELL_MAX_CHARS]


def _row(blocks: list[Block], draft: PriorRowDraft, used: list[Block]) -> dict:
    """논문 한 편의 표 행. 근거 라벨이 이 논문 블록에 없는 칸은 null로 버린다(근거 없는 값은 내보내지 않는다).
    쓰인 블록은 전역 라벨(S1..)을 새로 붙여 used에 더한다."""
    local = {b.label: b for b in blocks}
    cells = {c.key: c for c in draft.cells}
    row: dict = {"paper_id": blocks[0].paper_id, "title": blocks[0].title, "labels": {}}
    mapping: dict[str, str] = {}
    for key in COLUMNS:
        cell = cells.get(key)
        value = _clean(cell.value) if cell else None
        if value and cell.label in local:
            if cell.label not in mapping:
                mapping[cell.label] = f"S{len(used) + 1}"
                used.append(replace(local[cell.label], label=mapping[cell.label]))
            row[key] = value
            row["labels"][key] = mapping[cell.label]
        else:
            row[key] = None
    return row


def _table_text(rows: list[dict]) -> str:
    lines = []
    for row in rows:
        lines.append(f"《{row['title']}》")
        for key in COLUMNS:
            if row[key]:
                lines.append(f"- {PRIOR_COLUMN_NAMES[key]}: {row[key]} [{row['labels'][key]}]")
    return "\n".join(lines)


def run(req: RagRequest, user: CurrentUser, usage: dict | None = None) -> RagResponse:
    started = time.monotonic()
    level = req.level or "L2"
    view = req.view or user.view or "dev"
    in_tok = out_tok = 0
    rows: list[dict] = []
    used: list[Block] = []
    failures: list[ApiError] = []

    evidence = {pid: _evidence(user.team_id, pid) for pid in _paper_ids(req, user.team_id)}
    papers = [(pid, build_blocks(hits)) for pid, hits in evidence.items() if hits]

    if papers:
        with ThreadPoolExecutor(max_workers=max(1, config_rag.PRIOR_WORKERS)) as pool:
            results = list(pool.map(lambda p: _extract_safe(p[1]), papers))
        for (_, blocks), (draft, i, o, error) in zip(papers, results):
            in_tok, out_tok = in_tok + i, out_tok + o
            if error is not None:
                failures.append(error)
            else:
                rows.append(_row(blocks, draft, used))
        if not rows and failures:
            raise failures[0]  # 모든 논문이 실패했다면 '근거 없음'이 아니라 실패다

    if not used:
        resp = _not_found(level, view)
    else:
        fallback = f"선택한 {len(rows)}편을 정리표로 비교했어요. 칸마다 근거 쪽수를 확인하세요."
        review = False
        try:
            system = PRIOR_COMPARE_PROMPT.format(level_rules=LEVEL_RULES[level], view_rules=VIEW_RULES[view])
            draft, i, o = llm.generate_structured(system, PRIOR_COMPARE_USER.format(table=_table_text(rows), question=req.question), AnswerDraft)
            in_tok, out_tok = in_tok + i, out_tok + o
            if draft.found and draft.answer.strip():
                answer = draft.answer
                _, citation_failed = verify_citations(answer, draft.cited, used)
                review = citation_failed
            else:
                answer, review = fallback, True
        except ApiError:
            answer, review = fallback, True  # 표는 이미 만들었으므로 비교 문단만 대신한다
        if failures:
            answer += f" ({len(failures)}편은 정리하지 못했어요. 잠시 후 다시 시도해 주세요.)"
        resp = RagResponse(
            answer=answer,
            sources=source_strings(used),
            source_details=details_of(used),
            needs_review=review or bool(failures) or any(_DIGIT_RE.search(row[k] or "") for row in rows for k in COLUMNS),
            level=level,
            view=view,
            latency_ms=0,
            table=rows,
        )

    if usage is not None:
        usage["in_tok"], usage["out_tok"] = in_tok, out_tok
        usage["images"], usage["retry"] = 0, "none"
    resp.latency_ms = int((time.monotonic() - started) * 1000)
    # 질문·답변 원문은 로그에 남기지 않는다 (건수·토큰·지연만)
    logger.info(
        "rag-prior papers=%d rows=%d failed=%d handoff=%s in_tok=%d out_tok=%d latency_ms=%d",
        len(papers), len(rows), len(failures), resp.handoff, in_tok, out_tok, resp.latency_ms,
    )
    return resp
