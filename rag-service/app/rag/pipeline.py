"""검색→답변 파이프라인 (DEV_04 3절).

요청 → 깊이(level)/view 결정 → store.search → MIN_SCORE 필터
  → 0건: 근거 없음(LLM 미호출)
  → 있음: 컨텍스트 → 프롬프트 → LLM 구조화 출력 → 인용 검증 → needs_review → 응답
"""
import logging
import re
import time

from app.rag import config_rag, llm, page_images
from app.rag.context import Block, build_blocks, render_context
from app.rag.deps import CurrentUser, store
from app.rag.prompts import IMAGE_NOTE, LEVEL_RULES, SYSTEM_PROMPT, USER_PROMPT, VIEW_RULES
from app.rag.schemas import RagRequest, RagResponse, SourceDetail

logger = logging.getLogger("rag")

# source 요청값 → 스토어 목록 (DEV_03 6절)
SOURCE_MAP = {
    "pdf": ["pdf", "annotation"],
    "web": ["web"],
    "all": ["pdf", "web", "annotation"],
}

NOT_FOUND_ANSWER = "팀 라이브러리에서 관련 내용을 찾을 수 없습니다."
WITHHELD_ANSWER = ("표·그림·수식에 있는 값을 원본 페이지에서 확인하지 못해 수치는 답하지 않습니다. "
                   "아래 출처의 원본 페이지를 직접 확인해 주세요.")

_LABEL_RE = re.compile(r"\[(S\d+)\]")
_MATH_RE = re.compile(r"\$|%|\d+\.\d+")
# 이미지 재시도 조건: 답변에 백분율·소수·수식 기호·두 자리 이상 숫자가 있음
_VALUE_RE = re.compile(r"\d+(\.\d+)?\s*%|\d+\.\d+|\$|\d{2,}")


def _not_found(level: str, view: str) -> RagResponse:
    return RagResponse(answer=NOT_FOUND_ANSWER, handoff=True, level=level, view=view, latency_ms=0)


def _details(blocks: list[Block]) -> list[SourceDetail]:
    return [
        SourceDetail(
            label=b.label,
            paper_id=b.paper_id,
            title=b.title,
            page=b.page,
            url=b.url,
            snippet=b.text[:200],
        )
        for b in blocks
    ]


def _source_strings(blocks: list[Block]) -> list[str]:
    seen: list[str] = []
    for b in blocks:
        s = f"{b.title} p.{b.page}" if b.page is not None else b.title
        if s not in seen:
            seen.append(s)
    return seen


def verify_citations(answer: str, cited: list[str], blocks: list[Block]) -> tuple[list[Block], bool]:
    """인용 검증. 반환: (출처로 쓸 블록, 인용 검증 실패 여부).

    - 존재하지 않는 라벨을 인용했거나 본문에 라벨이 하나도 없으면 실패
    - 검증된 라벨이 0개이면 컨텍스트 블록 전체를 출처로 돌려준다 (출처가 비지 않도록)
    """
    valid = {b.label for b in blocks}
    in_answer = set(_LABEL_RE.findall(answer))
    failed = (not in_answer) or any(c not in valid for c in cited) or any(l not in valid for l in in_answer)
    ok = [c for c in dict.fromkeys(cited) if c in valid]
    used = [b for b in blocks if b.label in ok] or blocks
    return used, failed


def needs_review(answer: str, used: list[Block], citation_failed: bool, top_score: float) -> bool:
    """DEV_04 3.5절: 하나라도 해당하면 True."""
    return (
        any(b.has_math for b in used)
        or bool(_MATH_RE.search(answer))
        or citation_failed
        or top_score < config_rag.REVIEW_SCORE
        or all(b.type == "annotation" for b in used)
    )


def retry_blocks(answer: str, blocks: list[Block]) -> list[Block]:
    """이미지 재시도 대상: 답변이 인용한 블록 중 표·그림·수식 표시(visual)가 붙은 것. 답에 수치·수식이 없으면 빈 목록."""
    if not _VALUE_RE.search(answer):
        return []
    cited = set(_LABEL_RE.findall(answer))
    return [b for b in blocks if b.label in cited and b.visual]


def limit_captions(hits: list, k: int, max_captions: int | None) -> list:
    """상위 k개 안에서 캡션 청크를 max_captions개까지만 남긴다 (캡션이 본문 자리를 차지하지 않도록). None이면 제한 없음."""
    if max_captions is None:
        return hits[:k]
    out, caps = [], 0
    for h in hits:
        if h.metadata.get("kind") == "caption":
            if caps >= max_captions:
                continue
            caps += 1
        out.append(h)
        if len(out) == k:
            break
    return out


def _image_retry(system: str, user_msg: str, team_id: int, target: list[Block]):
    """target 블록의 원본 페이지로 다시 답한다. 반환: (draft 또는 None, 쓴 이미지, 입력 토큰, 출력 토큰). 이미지가 없으면 draft None."""
    images = page_images.pick_pages(team_id, target)
    if not images:
        return None, [], 0, 0
    img_msg = user_msg + "\n\n" + IMAGE_NOTE.format(labels=", ".join(f"[{l}]" for l, _ in images))
    draft, i, o = llm.generate(system, img_msg, images=images)
    return draft, images, i, o


def run(req: RagRequest, user: CurrentUser, usage: dict | None = None) -> RagResponse:
    started = time.monotonic()
    # v0.2: 사용자 수준 설정은 없다. level은 '더 쉽게/더 깊게' 요청이 body로 보낼 때만 오고(L1/L3), 없으면 기본 깊이(L2 규칙)다.
    level = req.level or "L2"
    view = req.view or user.view or "dev"

    # team_id는 JWT에서만 읽는다 (요청 본문 값 무시)
    extra = config_rag.MAX_CAPTION_HITS is not None
    hits = store.search(
        user.team_id,
        SOURCE_MAP[req.source],
        req.question,
        k=req.top_k + (3 if extra else 0),  # 캡션을 덜어낼 만큼 여유 있게 받는다
        paper_ids=req.scope.ids if req.scope.type == "paper" else None,
        tags=req.scope.tags if req.scope.type == "tag" else None,
    )
    hits = limit_captions([h for h in hits if h.score >= config_rag.MIN_SCORE], req.top_k, config_rag.MAX_CAPTION_HITS)

    in_tok = out_tok = 0
    images: list = []
    retry = "none"
    if not hits:
        resp = _not_found(level, view)
    else:
        blocks = build_blocks(hits)
        system = SYSTEM_PROMPT.format(level_rules=LEVEL_RULES[level], view_rules=VIEW_RULES[view])
        user_msg = USER_PROMPT.format(context=render_context(blocks), question=req.question)
        draft, in_tok, out_tok = llm.generate(system, user_msg)

        # 이미지 재시도 (DEV_04 밖의 확장, PAGE_IMAGES=on일 때만)
        #  - 텍스트 답이 표·그림·수식 블록을 인용해 수치·수식을 말했으면 그 원본 페이지로 다시 답한다
        #  - 재시도가 값을 확인하지 못하면(found=false) 텍스트 답의 수치를 내보내지 않고 원본 페이지만 안내한다
        #  - 텍스트가 거절한 경우는 PAGE_IMAGES_ON_REFUSAL=on일 때만 재시도 (근거 없는 질문에 답하는 위험이 있어 실험용)
        withheld: list[Block] = []
        if config_rag.PAGE_IMAGES and draft.found:
            target = retry_blocks(draft.answer, blocks)
            retried, images, i2, o2 = _image_retry(system, user_msg, user.team_id, target)
            in_tok, out_tok = in_tok + i2, out_tok + o2
            if retried is not None and retried.found:
                draft, retry = retried, "answered"
            elif retried is not None:
                withheld = [b for b in blocks if b.label in {l for l, _ in images}]
                retry = "withheld"
        elif config_rag.PAGE_IMAGES and config_rag.PAGE_IMAGES_ON_REFUSAL:
            retried, images, i2, o2 = _image_retry(system, user_msg, user.team_id, [b for b in blocks if b.visual])
            in_tok, out_tok = in_tok + i2, out_tok + o2
            if retried is not None and retried.found:
                draft, retry = retried, "refusal_answered"

        if withheld:
            resp = RagResponse(
                answer=WITHHELD_ANSWER,
                sources=_source_strings(withheld),
                source_details=_details(withheld),
                needs_review=True,
                level=level,
                view=view,
                latency_ms=0,
            )
        elif not draft.found:
            resp = _not_found(level, view)
        else:
            used, failed = verify_citations(draft.answer, draft.cited, blocks)
            top_score = max(h.score for h in hits)
            resp = RagResponse(
                answer=draft.answer,
                sources=_source_strings(used),
                source_details=_details(used),
                # 이미지에서 읽은 값은 텍스트 근거로 대조할 수 없으므로 검수 대상으로 둔다
                needs_review=needs_review(draft.answer, used, failed, top_score) or bool(images),
                level=level,
                view=view,
                latency_ms=0,
            )

    if usage is not None:
        usage["in_tok"], usage["out_tok"] = in_tok, out_tok
        usage["images"] = len(images)
        usage["retry"] = retry
    resp.latency_ms = int((time.monotonic() - started) * 1000)
    # 질문·답변 원문은 로그에 남기지 않는다 (건수·토큰·지연만)
    logger.info(
        "rag-query hits=%d handoff=%s in_tok=%d out_tok=%d latency_ms=%d",
        len(hits), resp.handoff, in_tok, out_tok, resp.latency_ms,
    )
    return resp
