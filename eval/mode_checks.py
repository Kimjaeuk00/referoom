"""모드별 평가 질문 검증·요청 생성·응답 검사 (순수 함수, 네트워크·LLM 없음).

tutor는 기존 방식(핵심어·근거 페이지·거절)을 run_eval.py가 그대로 처리하고, 이 모듈은 prior·topic·verify를 다룬다.
검사는 모두 규칙으로 판정한다(정규식·라벨 존재·판정 값). 질문·답변 원문은 결과에 남기지 않고 개수만 detail에 적는다.
"""
import re
import unicodedata

MODES = ("tutor", "prior", "topic", "verify")
ENDPOINT = {"tutor": "/rag-query", "prior": "/rag-query", "topic": "/topic-suggest", "verify": "/verify"}
COLUMNS = ("problem", "method", "dataset", "metric", "result", "limitation")
VERDICTS = ("match", "mismatch", "condition_differs", "not_found", "own_result")
GROUNDED_VERDICTS = ("match", "mismatch", "condition_differs")  # 근거 라벨이 있어야 하는 판정
MAX_TOPIC_PAPERS = 10


def title_key(title: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", title).casefold().split())


def _texts(value, *, minimum=1) -> bool:
    return isinstance(value, list) and len(value) >= minimum and all(isinstance(v, str) and v.strip() for v in value)


def validate_item(item: dict) -> None:
    """모드별 필수 필드를 검사한다. 잘못되면 ValueError(자세한 내용은 남기지 않는다)."""
    mode = item["mode"]
    if mode == "prior":
        if not item["should_refuse"]:
            if not _texts(item.get("expected_papers")):
                raise ValueError
            cells = item.get("expected_cells", [])
            if not isinstance(cells, list):
                raise ValueError
            for cell in cells:
                if not isinstance(cell, dict) or set(cell) != {"paper", "column", "pattern"}:
                    raise ValueError
                if cell["column"] not in COLUMNS or not _texts([cell["paper"], cell["pattern"]]):
                    raise ValueError
                try:
                    re.compile(cell["pattern"])
                except re.error:
                    raise ValueError from None  # 불러오기 쪽이 ValueError만 처리한다
        return
    if item["should_refuse"]:
        raise ValueError  # 거절 기대는 tutor·prior만 쓴다(topic·verify는 근거 없음을 판정 값으로 표현한다)
    if mode == "topic":
        if not _texts(item.get("papers")) or len(item["papers"]) > MAX_TOPIC_PAPERS:
            raise ValueError
        for key in ("min_topics", "n"):
            if key in item and (type(item[key]) is not int or not 1 <= item[key] <= 5):
                raise ValueError
        if "hint" in item and not isinstance(item["hint"], str):
            raise ValueError
    elif mode == "verify":
        claims = item.get("expected_claims")
        if not isinstance(claims, list) or not claims:
            raise ValueError
        for claim in claims:
            if not isinstance(claim, dict) or set(claim) != {"contains", "verdicts"}:
                raise ValueError
            if not _texts([claim["contains"]]) or not _texts(claim["verdicts"]) or not set(claim["verdicts"]) <= set(VERDICTS):
                raise ValueError
        if not 10 <= len(item["question"]) <= 1000:
            raise ValueError  # 서버 검증 하한은 10자


def build_request(item: dict, top_k: int, paper_ids: list[int] | None = None) -> tuple[str, dict]:
    """(경로, JSON body). topic은 논문 제목을 id로 바꾼 paper_ids가 필요하다."""
    mode = item["mode"]
    if mode == "topic":
        return ENDPOINT[mode], {"paper_ids": paper_ids or [], "hint": item.get("hint", ""),
                                "n": item.get("n", 3), "view": item["view"]}
    if mode == "verify":
        return ENDPOINT[mode], {"text": item["question"], "view": item["view"]}
    body = {"question": item["question"], "view": item["view"], "top_k": top_k}
    if mode == "prior":
        body["mode"] = "prior"
    if item.get("level"):
        body["level"] = item["level"]
    for field in ("source", "scope"):
        if field in item:
            body[field] = item[field]
    return ENDPOINT[mode], body


def resolve_papers(titles: list[str], library: list[dict]) -> list[int] | None:
    """제목(부분 일치, 대소문자 무시)으로 라이브러리 논문 id를 찾는다. 하나라도 못 찾거나 모호하면 None."""
    ids: list[int] = []
    for title in titles:
        key = title_key(title)
        found = [p["id"] for p in library if isinstance(p.get("title"), str) and key in title_key(p["title"])]
        if len(found) != 1 or type(found[0]) is not int:
            return None
        ids.append(found[0])
    return ids


def _labels(body: dict) -> set:
    return {d.get("label") for d in body.get("source_details", []) if isinstance(d, dict)}


def valid_mode_response(mode: str, body) -> bool:
    """topic·verify 응답의 최소 구조(필드 존재·타입). prior는 /rag-query 공통 검증 뒤에 table만 본다."""
    if not isinstance(body, dict) or type(body.get("handoff")) is not bool or not isinstance(body.get("source_details"), list):
        return False
    if mode == "prior":
        return body.get("table") is None or (isinstance(body["table"], list) and all(isinstance(r, dict) for r in body["table"]))
    if mode == "topic":
        return all(isinstance(body.get(k), list) for k in ("limitations", "topics")) and type(body.get("needs_review")) is bool
    if mode == "verify":
        return (isinstance(body.get("claims"), list) and all(isinstance(c, dict) for c in body["claims"])
                and isinstance(body.get("draft"), str) and isinstance(body.get("warnings"), list))
    return False


def check(item: dict, body: dict) -> tuple[bool, str]:
    """응답이 기대와 맞는지. 반환: (통과, 개수만 담은 요약)."""
    return {"prior": _check_prior, "topic": _check_topic, "verify": _check_verify}[item["mode"]](item, body)


def _check_prior(item, body):
    rows = body.get("table") or []
    if item["should_refuse"]:
        ok = body["handoff"] and not rows and not body.get("sources") and not body["source_details"]
        return ok, f"refused={'yes' if ok else 'no'}"
    if body["handoff"]:
        return False, "handoff"
    keys = [title_key(str(r.get("title", ""))) for r in rows]
    papers = sum(any(title_key(p) in key for key in keys) for p in item["expected_papers"])
    cells = item.get("expected_cells", [])
    cell_hits = 0
    for spec in cells:
        for row, key in zip(rows, keys):
            value = row.get(spec["column"])
            if title_key(spec["paper"]) in key and isinstance(value, str) and re.search(spec["pattern"], value, re.IGNORECASE):
                cell_hits += 1
                break
    known = _labels(body)
    grounded = all(
        isinstance(row.get("labels"), dict) and row["labels"].get(col) in known
        for row in rows for col in COLUMNS if row.get(col)
    )
    ok = papers == len(item["expected_papers"]) and cell_hits == len(cells) and grounded
    return ok, f"papers={papers}/{len(item['expected_papers'])};cells={cell_hits}/{len(cells)};labels={'ok' if grounded else 'bad'}"


def _check_topic(item, body):
    if body["handoff"]:
        return False, "handoff"
    topics, known = body["topics"], _labels(body)
    need = item.get("min_topics", 1)
    grounded = all(t.get("based_on") and set(t["based_on"]) <= known for t in topics) and all(
        lim.get("label") in known for lim in body["limitations"]
    )
    perspectives = [t.get("perspective") for t in topics]
    distinct = len(set(perspectives)) == len(perspectives)
    ok = len(topics) >= need and grounded and distinct
    return ok, f"topics={len(topics)}/{need};labels={'ok' if grounded else 'bad'};perspectives={'distinct' if distinct else 'dup'}"


def _check_verify(item, body):
    # verify는 비교할 근거를 하나도 못 찾으면 handoff를 켜고 주장을 not_found로 돌려준다.
    # 그래서 기대 판정이 모두 not_found를 허용할 때만 handoff를 실패로 보지 않는다.
    if body["handoff"] and not all("not_found" in spec["verdicts"] for spec in item["expected_claims"]):
        return False, "handoff"
    claims, known = body["claims"], _labels(body)
    hits = 0
    for spec in item["expected_claims"]:
        needle = spec["contains"].casefold()
        if any(
            needle in f"{c.get('sentence', '')} {c.get('subject', '')}".casefold() and c.get("verdict") in spec["verdicts"]
            for c in claims
        ):
            hits += 1
    grounded = all(
        c.get("labels") and set(c["labels"]) <= known for c in claims if c.get("verdict") in GROUNDED_VERDICTS
    )
    ok = hits == len(item["expected_claims"]) and grounded
    return ok, f"claims={hits}/{len(item['expected_claims'])};labels={'ok' if grounded else 'bad'}"
