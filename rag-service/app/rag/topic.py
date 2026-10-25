"""주제 모드 (POST /topic-suggest): 선택한 논문들의 한계를 근거로 연구 주제 후보를 제안한다.

흐름
  1. 대상 논문: 요청의 paper_ids 중 이 팀 색인에 있는 것만(다른 팀·없는 id는 말없이 제외)
  2. 논문마다 '한계·향후 연구' 질의로 근거를 모아 [S#] 블록으로 만들고, 구조화 추출 1회(병렬)로 한계를 뽑는다.
     근거 라벨이 이 논문 블록에 없는 한계는 버린다. 쓰인 블록에는 응답 전체에서 쓰는 전역 라벨(S1..)을 붙인다
  3. 한계가 하나도 없으면 LLM을 더 부르지 않고 handoff
  4. 찾은 한계만 근거로 후보를 한 번에 생성한다(관점은 후보마다 서로 달라야 한다). 근거 라벨이 없거나 존재하지 않는
     후보는 버린다
  5. 후보마다 선택하지 않은 라이브러리 논문 중 비슷한 연구를 찾아 붙인다(임계값 TOPIC_SIMILAR_MIN_SCORE)
후보는 AI의 제안이므로 needs_review는 항상 True다. 방향(hint)과 후보 문장은 로그에 남기지 않는다.
"""
import logging
import time

from app.rag import config_rag, llm
from app.rag.context import Block, build_blocks, details_of, render_context, source_strings
from app.rag.deps import CurrentUser, store
from app.rag.modes import adopt_block, clean_text, map_safe
from app.rag.prompts import (
    TOPIC_LIMIT_PROMPT, TOPIC_LIMIT_QUERY, TOPIC_LIMIT_USER, TOPIC_PERSPECTIVES, TOPIC_SUGGEST_PROMPT, TOPIC_SUGGEST_USER, VIEW_RULES,
)
from app.rag.schemas import (
    Experiment, Limitation, LimitationDraft, SimilarPaper, TopicCandidate, TopicDraft, TopicRequest, TopicResponse,
)

logger = logging.getLogger("rag")


def _evidence(team_id: int, paper_id: int) -> list:
    hits = store.chunks_of_paper(team_id, paper_id, TOPIC_LIMIT_QUERY, k=config_rag.TOPIC_CHUNKS_PER_PAPER)
    return sorted(hits, key=lambda h: h.metadata.get("page") or 0)


def _extract(blocks: list[Block]) -> tuple[LimitationDraft, int, int]:
    system = TOPIC_LIMIT_PROMPT.format(max_items=config_rag.TOPIC_LIMITS_PER_PAPER)
    user = TOPIC_LIMIT_USER.format(context=render_context(blocks), title=blocks[0].title)
    return llm.generate_structured(system, user, LimitationDraft)


def _limitations(blocks: list[Block], draft: LimitationDraft, used: list[Block]) -> list[Limitation]:
    """한 논문의 한계. 근거 라벨이 이 논문 블록에 없거나 같은 블록을 두 번 쓴 항목은 버린다(블록마다 한계 하나)."""
    local = {b.label: b for b in blocks}
    out: list[Limitation] = []
    seen: set[str] = set()
    for item in draft.items:
        summary = clean_text(item.summary, config_rag.TOPIC_TEXT_MAX_CHARS)
        if not summary or item.label not in local or item.label in seen:
            continue
        seen.add(item.label)
        block = local[item.label]
        out.append(Limitation(label=adopt_block(used, block), paper_id=block.paper_id, title=block.title, page=block.page, summary=summary))
        if len(out) >= config_rag.TOPIC_LIMITS_PER_PAPER:
            break
    return out


def _suggest(limitations: list[Limitation], req: TopicRequest, view: str) -> tuple[TopicDraft, int, int]:
    perspectives = "\n".join(f"- {key}: {text}" for key, text in TOPIC_PERSPECTIVES.items())
    system = TOPIC_SUGGEST_PROMPT.format(n=req.n, perspectives=perspectives, view_rules=VIEW_RULES[view])
    lines = [
        f"- [{lim.label}] 《{lim.title}》{f' p.{lim.page}' if lim.page is not None else ''}: {lim.summary}"
        for lim in limitations
    ]
    user = TOPIC_SUGGEST_USER.format(limitations="\n".join(lines), hint=req.hint.strip() or "없음")
    return llm.generate_structured(system, user, TopicDraft)


def _names(values: list[str]) -> list[str]:
    cleaned = (clean_text(v, config_rag.TOPIC_TEXT_MAX_CHARS) for v in values)
    return [v for v in dict.fromkeys(cleaned) if v][: config_rag.TOPIC_LIST_MAX_ITEMS]


def _candidates(draft: TopicDraft, valid_labels: set[str], n: int) -> list[TopicCandidate]:
    """근거 없는 후보와 같은 관점의 중복 후보를 버리고 n개까지만 남긴다. 존재하지 않는 근거 라벨은 뺀다."""
    out: list[TopicCandidate] = []
    perspectives: set[str] = set()
    for t in draft.topics:
        limit = config_rag.TOPIC_TEXT_MAX_CHARS
        title, question, approach = clean_text(t.title, limit), clean_text(t.question, limit), clean_text(t.approach, limit)
        based_on = [label for label in dict.fromkeys(t.based_on) if label in valid_labels]
        if t.perspective in perspectives or not (title and question and approach and based_on):
            continue
        perspectives.add(t.perspective)
        out.append(TopicCandidate(
            perspective=t.perspective, title=title, question=question, approach=approach,
            experiment=Experiment(datasets=_names(t.datasets), baselines=_names(t.baselines), metrics=_names(t.metrics)),
            based_on=based_on,
        ))
        if len(out) >= n:
            break
    return out


def _similar(team_id: int, topic: TopicCandidate, selected: set[int]) -> list[SimilarPaper]:
    """선택하지 않은 라이브러리 논문 중 후보와 비슷한 것. 후보의 제목+질문과 청크의 유사도가 임계값 이상일 때만."""
    try:
        hits = store.search(
            team_id, ["pdf"], f"{topic.title}\n{topic.question}", k=config_rag.TOPIC_SIMILAR_SEARCH_K,
            min_score=config_rag.TOPIC_SIMILAR_MIN_SCORE,
        )
    except Exception as e:  # 유사 연구는 덧붙이는 정보다. 실패해도 후보 자체는 돌려준다(종류만 기록)
        logger.error("topic similar search failed: %s", type(e).__name__)
        return []
    best: dict[int, tuple[float, str]] = {}
    for h in hits:
        pid = h.metadata.get("paper_id")
        if pid is None or pid in selected or (pid in best and best[pid][0] >= h.score):
            continue
        best[pid] = (h.score, h.metadata.get("source", ""))
    ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[: config_rag.TOPIC_SIMILAR_MAX]
    return [SimilarPaper(paper_id=pid, title=title, score=round(score, 2)) for pid, (score, title) in ranked]


def run(req: TopicRequest, user: CurrentUser, usage: dict | None = None) -> TopicResponse:
    started = time.monotonic()
    view = req.view or user.view or "dev"
    in_tok = out_tok = 0
    used: list[Block] = []
    limitations: list[Limitation] = []
    failures = []

    indexed = store.paper_chunk_counts(user.team_id)
    ids = [pid for pid in dict.fromkeys(req.paper_ids) if pid in indexed][: config_rag.TOPIC_MAX_PAPERS]
    papers = [build_blocks(hits) for hits in (_evidence(user.team_id, pid) for pid in ids) if hits]

    succeeded = 0
    if papers:
        for blocks, (out, error) in zip(papers, map_safe(_extract, papers, config_rag.TOPIC_WORKERS)):
            if error is not None:
                failures.append(error)
                continue
            draft, i, o = out
            in_tok, out_tok = in_tok + i, out_tok + o
            succeeded += 1
            limitations.extend(_limitations(blocks, draft, used))
        if not succeeded:
            raise failures[0]  # 모든 논문의 추출이 실패했다면 '근거 없음'이 아니라 실패다

    topics: list[TopicCandidate] = []
    if limitations:
        draft, i, o = _suggest(limitations, req, view)  # 실패하면 후보가 없으므로 오류로 응답한다
        in_tok, out_tok = in_tok + i, out_tok + o
        topics = _candidates(draft, {lim.label for lim in limitations}, req.n)
        selected = set(ids)
        for topic in topics:
            topic.similar_papers = _similar(user.team_id, topic, selected)

    if topics:
        resp = TopicResponse(
            limitations=limitations, topics=topics, sources=source_strings(used), source_details=details_of(used),
            needs_review=True, handoff=False, view=view, latency_ms=0,
        )
    else:
        resp = TopicResponse(handoff=True, view=view, latency_ms=0)

    if usage is not None:
        usage["in_tok"], usage["out_tok"] = in_tok, out_tok
    resp.latency_ms = int((time.monotonic() - started) * 1000)
    # 방향(hint)과 후보 문장은 로그에 남기지 않는다 (건수·토큰·지연만)
    logger.info(
        "rag-topic papers=%d limits=%d topics=%d failed=%d handoff=%s in_tok=%d out_tok=%d latency_ms=%d",
        len(papers), len(limitations), len(topics), len(failures), resp.handoff, in_tok, out_tok, resp.latency_ms,
    )
    return resp
