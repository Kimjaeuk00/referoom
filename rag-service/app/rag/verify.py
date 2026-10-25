"""검증 모드 (POST /verify): 원고의 수치 주장을 선행연구 근거와 대조한다.

흐름
  1. 대조할 논문 범위 정하기: paper_ids가 있으면 이 팀 색인에 있는 것만(없는 id는 제외, 전부 없으면 전체로 넓히지 않고 근거 없음),
     없으면 팀 전체. 비교할 논문이 하나도 없으면 원고를 LLM에 보내지 않고 바로 handoff
  2. 원고에서 수치 주장 추출(LLM 1회). 상한(VERIFY_MAX_CLAIMS)을 넘으면 앞에서부터 처리하고 warnings로 알린다
  3. 주장마다 근거 검색 → 비교할 값 읽기(LLM, 주장별 병렬)
  4. 판정은 LLM이 아니라 코드가 한다(numeric.py): 값이 같으면 match, 다르면 mismatch, 조건이 다르거나 비교할 수 없으면
     condition_differs, 근거가 없으면 not_found, 원고 저자 본인의 결과면 own_result(+ 선행 값과의 차이). 애매하면 match로 내보내지 않는다
  5. 근거 라벨이 붙은 비교 문장 초안을 쓰고 인용을 검증한다(검증에 실패하면 초안은 내지 않는다)
needs_review는 항상 True다(수치를 다룬다). 원고와 주장 문장은 LLM 요청에만 쓰고 로그·예외 메시지에는 남기지 않는다(건수·토큰·지연만).
"""
import logging
import re
import time
from dataclasses import dataclass

from app.rag import config_rag, llm
from app.rag.context import Block, build_blocks, details_of, render_context, source_strings, verify_citations
from app.rag.deps import CurrentUser, store
from app.rag.errors import ApiError
from app.rag.modes import adopt_block, clean_text, map_safe
from app.rag.numeric import compare_values, difference
from app.rag.prompts import (
    VERDICT_KO, VERIFY_DRAFT_PROMPT, VERIFY_DRAFT_USER, VERIFY_EXTRACT_PROMPT, VERIFY_EXTRACT_USER, VERIFY_READ_PROMPT,
    VERIFY_READ_USER, VIEW_RULES,
)
from app.rag.schemas import (
    AnswerDraft, Claim, ClaimExtraction, Delta, EvidenceRead, ExtractedClaim, VerifyRequest, VerifyResponse,
)

logger = logging.getLogger("rag")

NOT_FOUND_WARNING = "라이브러리에서 비교할 값을 찾지 못했어요. 선행연구 모드로 해당 논문을 먼저 모아 주세요."
NO_CLAIMS_WARNING = "원고에서 선행연구와 비교할 수치 주장을 찾지 못했어요."
GENERIC_CONDITION = "조건이 달라 직접 비교하기 어려워요."
READ_FAILED_CONDITION = "확인 중 오류가 나서 비교하지 못했어요."

_NAME_RE = re.compile(r"[^0-9a-z가-힣]")


@dataclass
class Judgement:
    verdict: str
    found_value: str | None = None
    condition: str | None = None
    delta: Delta | None = None


def _datasets_conflict(claimed: str | None, found: str | None) -> bool:
    """두 쪽 모두 데이터셋·조건 이름이 있고 서로 포함 관계도 아니면 충돌로 본다(알 수 없으면 충돌이 아니다)."""
    a, b = _NAME_RE.sub("", (claimed or "").lower()), _NAME_RE.sub("", (found or "").lower())
    return bool(a and b and a not in b and b not in a)


def judge(claim: ExtractedClaim, read: EvidenceRead | None) -> Judgement:
    """한 주장의 판정. read는 근거에서 값을 읽은 결과이고, 근거가 없거나 읽지 못했으면 None.

    보수적으로 판정한다: 값이 같아도 근거의 조건이 다르다고 읽혔거나 데이터셋이 충돌하면 match가 아니라 condition_differs,
    숫자를 비교할 수 없으면(단위 종류가 다르거나 숫자가 아님) condition_differs다.
    """
    found = clean_text(read.found_value, config_rag.VERIFY_TEXT_MAX_CHARS) if read else None
    if not found:
        return Judgement("own_result" if claim.own_result else "not_found")
    condition = clean_text(read.condition, config_rag.VERIFY_TEXT_MAX_CHARS)
    comparable = read.same_conditions != "no" and not _datasets_conflict(claim.dataset, read.found_dataset)

    if claim.own_result:  # 본인 결과는 검증 대상이 아니다. 비교할 수 있는 선행 값이 있을 때만 차이를 계산한다
        value = difference(claim.claimed_value, found) if comparable else None
        delta = Delta(vs=clean_text(read.found_subject, config_rag.VERIFY_TEXT_MAX_CHARS), value=value) if value is not None else None
        return Judgement("own_result", found, condition, delta)

    outcome = compare_values(claim.claimed_value, found)
    if not comparable or outcome == "unsure":
        return Judgement("condition_differs", found, condition or GENERIC_CONDITION)
    return Judgement("match" if outcome == "equal" else "mismatch", found, condition)


def _scope_ids(req: VerifyRequest, team_id: int) -> list[int] | None:
    """대조할 논문 id. None이면 팀 전체, 빈 목록이면 대조할 논문이 없다."""
    indexed = store.paper_chunk_counts(team_id)
    if req.paper_ids is None:
        return None if indexed else []
    return [pid for pid in dict.fromkeys(req.paper_ids) if pid in indexed]


def _evidence(team_id: int, claim: ExtractedClaim, ids: list[int] | None) -> list[Block]:
    query = " ".join(p for p in (claim.subject, claim.metric, claim.dataset, claim.claimed_value) if p) or claim.sentence
    hits = store.search(team_id, ["pdf"], query, k=config_rag.VERIFY_EVIDENCE_CHUNKS, paper_ids=ids, min_score=config_rag.MIN_SCORE)
    return build_blocks(hits)


def _read(claim: ExtractedClaim, blocks: list[Block]) -> tuple[EvidenceRead, int, int]:
    none = "없음"
    user = VERIFY_READ_USER.format(
        context=render_context(blocks), subject=claim.subject or none, metric=claim.metric or none,
        dataset=claim.dataset or none, claimed_value=claim.claimed_value or none, sentence=claim.sentence,
        kind="본인 결과" if claim.own_result else "선행연구 값 인용",
    )
    return llm.generate_structured(VERIFY_READ_PROMPT, user, EvidenceRead)


def _draft(rows: list[Claim], view: str) -> tuple[AnswerDraft, int, int]:
    lines = []
    for row in rows:
        found = f" / 논문 값 {row.found_value}" if row.found_value else ""
        delta = f" / 차이 {row.delta.value:+g} (비교 대상 {row.delta.vs or '선행 값'})" if row.delta else ""
        condition = f" / 조건: {row.condition}" if row.condition else ""
        lines.append(
            f"- [{row.labels[0]}] {VERDICT_KO[row.verdict]} · {row.subject or '대상 미상'} {row.metric or ''} · "
            f"원고 값 {row.claimed_value or '없음'}{found}{delta}{condition}"
        )
    system = VERIFY_DRAFT_PROMPT.format(view_rules=VIEW_RULES[view])
    return llm.generate_structured(system, VERIFY_DRAFT_USER.format(results="\n".join(lines)), AnswerDraft)


def run(req: VerifyRequest, user: CurrentUser, usage: dict | None = None) -> VerifyResponse:
    started = time.monotonic()
    view = req.view or user.view or "dev"
    in_tok = out_tok = 0
    warnings: list[str] = []
    rows: list[Claim] = []
    used: list[Block] = []
    failed = 0
    stats = {"claims": 0, "read": 0}

    ids = _scope_ids(req, user.team_id)
    if ids == []:
        # 대조할 논문이 하나도 없으면 원고를 LLM에 보내지 않는다(보낼 이유가 없다)
        resp = VerifyResponse(warnings=[NOT_FOUND_WARNING], handoff=True, view=view, latency_ms=0)
    else:
        extraction, i, o = llm.generate_structured(
            VERIFY_EXTRACT_PROMPT.format(max_claims=config_rag.VERIFY_MAX_CLAIMS), VERIFY_EXTRACT_USER.format(text=req.text), ClaimExtraction,
        )
        in_tok, out_tok = in_tok + i, out_tok + o
        claims = [c for c in extraction.claims if clean_text(c.sentence, config_rag.VERIFY_TEXT_MAX_CHARS)]
        if len(claims) > config_rag.VERIFY_MAX_CLAIMS:
            warnings.append(f"주장이 {len(claims)}개라 앞의 {config_rag.VERIFY_MAX_CLAIMS}개만 확인했어요.")
            claims = claims[: config_rag.VERIFY_MAX_CLAIMS]
        stats["claims"] = len(claims)

        if not claims:
            resp = VerifyResponse(warnings=[NO_CLAIMS_WARNING], handoff=True, view=view, latency_ms=0)
        else:
            evidence = [_evidence(user.team_id, c, ids) for c in claims]  # 임베딩을 쓰므로 한 스레드에서 차례로
            jobs = [(c, blocks) for c, blocks in zip(claims, evidence) if blocks]
            results = iter(map_safe(lambda job: _read(*job), jobs, config_rag.VERIFY_WORKERS))
            outcomes = [next(results) if blocks else None for blocks in evidence]
            stats["read"] = len(jobs)
            read_results = [o for o in outcomes if o is not None]
            if read_results and all(error is not None for _, error in read_results):
                raise read_results[0][1]  # 값을 읽는 호출이 모두 실패했다면 '근거 없음'이 아니라 실패다

            by_key: dict[tuple, str] = {}

            def adopt(block: Block) -> str:
                key = (block.paper_id, block.page, block.type)
                if key not in by_key:
                    by_key[key] = adopt_block(used, block)
                return by_key[key]

            for claim, blocks, outcome in zip(claims, evidence, outcomes):
                read, labels, judgement = None, [], None
                if outcome is not None:
                    out, error = outcome
                    if error is not None:
                        failed += 1
                        judgement = Judgement("own_result" if claim.own_result else "not_found", condition=READ_FAILED_CONDITION)
                    else:
                        read, i, o = out
                        in_tok, out_tok = in_tok + i, out_tok + o
                        local = {b.label: b for b in blocks}
                        if not (read.found_value and read.label in local):
                            read = None  # 값이나 근거 라벨이 없으면(또는 없는 라벨이면) 근거가 없는 것으로 본다
                        else:
                            labels = [adopt(local[read.label])]
                if judgement is None:
                    judgement = judge(claim, read)
                limit = config_rag.VERIFY_TEXT_MAX_CHARS
                rows.append(Claim(
                    sentence=clean_text(claim.sentence, limit), subject=clean_text(claim.subject, limit), metric=clean_text(claim.metric, limit),
                    claimed_value=clean_text(claim.claimed_value, limit), dataset=clean_text(claim.dataset, limit),
                    found_value=judgement.found_value, condition=judgement.condition, verdict=judgement.verdict,
                    labels=labels, delta=judgement.delta,
                ))

            draft_text = ""
            citable = [r for r in rows if r.labels]
            if citable:
                try:
                    draft, i, o = _draft(citable, view)
                    in_tok, out_tok = in_tok + i, out_tok + o
                    _, citation_failed = verify_citations(draft.answer, draft.cited, used)
                    if draft.found and draft.answer.strip() and not citation_failed:
                        draft_text = draft.answer
                    else:
                        warnings.append("비교 문장 초안의 근거 표시를 확인하지 못해 초안을 내지 않았어요.")
                except ApiError:
                    warnings.append("비교 문장 초안을 만들지 못했어요. 대조표는 그대로 확인할 수 있어요.")
            if failed:
                warnings.append(f"주장 {failed}개는 확인 중 오류가 나서 비교하지 못했어요. 잠시 후 다시 시도해 주세요.")
            handoff = not used
            if handoff:
                warnings.append(NOT_FOUND_WARNING)
            resp = VerifyResponse(
                claims=rows, draft=draft_text, warnings=warnings, sources=source_strings(used), source_details=details_of(used),
                needs_review=True, handoff=handoff, view=view, latency_ms=0,
            )

    if usage is not None:
        usage["in_tok"], usage["out_tok"] = in_tok, out_tok
    resp.latency_ms = int((time.monotonic() - started) * 1000)
    # 원고·주장 문장은 로그에 남기지 않는다 (건수·토큰·지연만)
    logger.info(
        "rag-verify claims=%d read=%d used=%d failed=%d handoff=%s in_tok=%d out_tok=%d latency_ms=%d",
        stats["claims"], stats["read"], len(used), failed, resp.handoff, in_tok, out_tok, resp.latency_ms,
    )
    return resp
