"""검증 모드(POST /verify): 원고 수치 주장 → 근거 읽기 → 코드 판정 → 비교 문장 초안. 가짜 LLM·색인으로 확인한다."""
import json
import logging

import pytest

from app.rag import config_rag, verify
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError
from app.rag.schemas import AnswerDraft, ClaimExtraction, EvidenceRead, ExtractedClaim, VerifyRequest
from app.rag.store_stub import Hit

USER = CurrentUser(user_id=12, username="tester", role="member", team_id=3, team_type="dev", view="dev")
TITLES = {41: "LoRA: Low-Rank Adaptation", 42: "QLoRA: Efficient Finetuning"}
SECRET = "비공개-원고-표식-8d3k"
MANUSCRIPT = f"본 연구의 방법은 GLUE 평균 88.1을 달성했다. LoRA는 학습 파라미터가 0.3M이다. {SECRET}"


def req(**kw):
    return VerifyRequest(**{"text": MANUSCRIPT, **kw})


def chunk(pid, page, text="본문", score=0.8):
    return Hit(text=text, score=score, metadata={"paper_id": pid, "source": TITLES[pid], "page": page, "type": "body"})


def claim(sentence, subject, value, own=False, metric="지표", dataset=None):
    return ExtractedClaim(sentence=sentence, subject=subject, metric=metric, claimed_value=value, dataset=dataset, own_result=own)


def read(value, label="S1", same="yes", subject=None, dataset=None, condition=None):
    return EvidenceRead(found_value=value, found_subject=subject, found_dataset=dataset, condition=condition, same_conditions=same, label=label)


@pytest.fixture()
def lib(monkeypatch):
    """색인이 있는 논문 {41, 42}. 검색은 질의에 든 이름에 맞는 논문의 청크를 돌려주고, 없는 이름은 아무것도 못 찾는다."""
    monkeypatch.setattr(verify.store, "paper_chunk_counts", lambda team_id: {41: 3, 42: 3})
    searches = []

    def search(team_id, sources, query, k=5, paper_ids=None, tags=None, min_score=None):
        searches.append({"team_id": team_id, "sources": sources, "query": query, "k": k, "paper_ids": paper_ids, "min_score": min_score})
        if "QLoRA" in query:
            return [chunk(42, 2, "QLoRA 본문")]
        if "LoRA" in query:
            return [chunk(41, 4, "LoRA 본문 4쪽"), chunk(41, 7, "LoRA 본문 7쪽")]
        return []

    monkeypatch.setattr(verify.store, "search", search)
    return searches


def prepare(fake_llm, claims, reads=None, draft=None):
    """reads: {대상 이름: EvidenceRead | 예외}. draft: 초안 AnswerDraft(또는 호출하면 예외를 던지는 함수)."""
    fake_llm.state["structured"][ClaimExtraction] = ClaimExtraction(claims=claims)

    def read_fn(system, user):
        subject = user.split("대상: ", 1)[1].split("\n", 1)[0]
        out = (reads or {})[subject]
        if isinstance(out, Exception):
            raise out
        return out

    fake_llm.state["structured"][EvidenceRead] = read_fn
    fake_llm.state["structured"][AnswerDraft] = draft if draft is not None else AnswerDraft(found=True, answer="초안 문장 [S1].", cited=["S1"])


FIVE = [
    claim("LoRA는 학습 파라미터가 0.3M이다", "LoRA", "0.3M", metric="trainable params"),            # 일치
    claim("QLoRA는 65B를 24GB GPU 한 장에서 학습한다", "QLoRA", "24GB", metric="GPU 메모리"),      # 불일치
    claim("LoRA는 GLUE 평균 87.2다", "LoRA GLUE", "87.2", metric="GLUE avg", dataset="RoBERTa-large"),  # 조건 다름
    claim("DoRA는 MMLU 71.2다", "DoRA", "71.2", metric="MMLU avg"),                              # 근거 없음
    claim("우리 방법은 GLUE 평균 88.1이다", "LoRA 비교", "88.1", own=True, metric="GLUE avg"),     # 본인 결과
]
READS = {
    "LoRA": read("300K", label="S1", same="yes", subject="LoRA"),
    "QLoRA": read("48GB", label="S1", same="yes", subject="QLoRA"),
    "LoRA GLUE": read("87.2", label="S2", same="no", subject="LoRA", dataset="RoBERTa-base", condition="RoBERTa-base 기준이에요."),
    "LoRA 비교": read("87.2", label="S2", same="yes", subject="LoRA"),
}


def test_five_verdicts_and_global_labels(fake_llm, lib):
    prepare(fake_llm, FIVE, READS)
    usage = {}
    r = verify.run(req(), USER, usage)
    verdicts = [c.verdict for c in r.claims]
    assert verdicts == ["match", "mismatch", "condition_differs", "not_found", "own_result"]
    match, mismatch, cond, missing, own = r.claims
    assert (match.found_value, mismatch.found_value) == ("300K", "48GB")
    assert cond.condition == "RoBERTa-base 기준이에요." and cond.found_value == "87.2"
    assert (missing.found_value, missing.labels, missing.delta) == (None, [], None)
    assert own.delta.value == 0.9 and own.delta.vs == "LoRA" and own.found_value == "87.2"
    # 라벨은 처음 쓰인 순서로 붙고, 같은 쪽을 가리키는 주장은 같은 라벨을 쓴다 (LoRA 4쪽 S1, QLoRA 2쪽 S2, LoRA 7쪽 S3)
    assert [c.labels for c in r.claims] == [["S1"], ["S2"], ["S3"], [], ["S3"]]
    assert [d.label for d in r.source_details] == ["S1", "S2", "S3"] and len(r.sources) == 3
    assert [(d.paper_id, d.page) for d in r.source_details] == [(41, 4), (42, 2), (41, 7)]
    # 응답 공통 규칙
    assert r.needs_review is True and r.handoff is False and r.view == "dev"
    assert r.draft == "초안 문장 [S1]."
    # 추출 1 + 근거 읽기 4(DoRA는 검색 결과가 없어 부르지 않는다) + 초안 1
    assert len(fake_llm.structured_calls) == 6 and (usage["in_tok"], usage["out_tok"]) == (600, 120)


def test_draft_labels_exist_in_source_details(fake_llm, lib):
    prepare(fake_llm, FIVE, READS, draft=AnswerDraft(found=True, answer="일치 [S1] 불일치 [S2] 조건 [S3]", cited=["S1", "S2", "S3"]))
    r = verify.run(req(), USER)
    assert r.draft and {d.label for d in r.source_details} >= {"S1", "S2", "S3"}
    # 초안 프롬프트에는 대조 결과의 값과 라벨만 들어간다 (원고 전문이 아니다)
    _, user, _ = [c for c in fake_llm.structured_calls if c[2] is AnswerDraft][0]
    assert "[S1] 일치" in user and "원고 값 24GB / 논문 값 48GB" in user and "차이 +0.9" in user and SECRET not in user


@pytest.mark.parametrize("bad", [
    AnswerDraft(found=True, answer="없는 근거 [S99]", cited=["S99"]),
    AnswerDraft(found=True, answer="라벨이 없는 문장", cited=[]),
    AnswerDraft(found=False, answer="", cited=[]),
])
def test_bad_draft_is_dropped_with_a_warning(fake_llm, lib, bad):
    prepare(fake_llm, FIVE, READS, draft=bad)
    r = verify.run(req(), USER)
    assert r.draft == "" and any("초안" in w for w in r.warnings) and len(r.claims) == 5  # 표는 그대로


def test_draft_failure_keeps_the_table(fake_llm, lib):
    def boom(system, user):
        raise ApiError(500, "INTERNAL_ERROR", "x")

    prepare(fake_llm, FIVE, READS, draft=boom)
    r = verify.run(req(), USER)
    assert r.draft == "" and any("초안을 만들지 못했어요" in w for w in r.warnings) and r.claims[0].verdict == "match"


# ---- judge: 코드 판정 ----

def c(value, own=False, dataset=None):
    return ExtractedClaim(sentence="s", subject="X", metric="m", claimed_value=value, dataset=dataset, own_result=own)


@pytest.mark.parametrize("claimed,found,extra,verdict", [
    ("87.2", "87.20", {}, "match"),
    ("0.872", "87.2%", {}, "match"),
    ("0.3M", "300K", {}, "match"),
    ("87.2", "87.2", {"same": "unknown"}, "match"),                      # 조건을 알 수 없어도 값이 같고 충돌이 없으면 일치
    ("87.2", "88.1", {}, "mismatch"),
    ("24GB", "48GB", {}, "mismatch"),
    ("87.2", "87.2", {"same": "no"}, "condition_differs"),               # 값이 같아도 조건이 다르면 일치가 아니다
    ("87.2", "87.2", {"dataset": "GLUE", "found_dataset": "SQuAD"}, "condition_differs"),   # 데이터셋 충돌
    ("87.2", "87.2", {"dataset": "GLUE", "found_dataset": "GLUE benchmark"}, "match"),       # 포함 관계는 충돌이 아니다
    ("87.2", "높은 편", {}, "condition_differs"),                         # 숫자가 아니면 비교하지 않는다
    ("24GB", "24M", {}, "condition_differs"),                            # 단위 종류가 다르다
    ("0.5", "0.5%", {}, "condition_differs"),                            # 비율인지 퍼센트인지 알 수 없다
    (None, "87.2", {}, "condition_differs"),                             # 원고에 값이 없다
])
def test_judge_is_conservative(claimed, found, extra, verdict):
    ev = read(found, same=extra.get("same", "yes"), dataset=extra.get("found_dataset"))
    j = verify.judge(c(claimed, dataset=extra.get("dataset")), ev)
    assert j.verdict == verdict
    if verdict == "condition_differs":
        assert j.condition  # 이유 문구가 항상 있다


def test_judge_without_evidence():
    assert verify.judge(c("1"), None).verdict == "not_found"
    assert verify.judge(c("1"), read(None)).verdict == "not_found"
    assert verify.judge(c("1"), read("  ")).verdict == "not_found"
    j = verify.judge(c("88.1", own=True), None)
    assert (j.verdict, j.delta) == ("own_result", None)  # 본인 결과는 근거가 없어도 본인 결과다


def test_judge_own_result_delta():
    j = verify.judge(c("88.1", own=True), read("87.2", subject="LoRA"))
    assert (j.verdict, j.delta.value, j.delta.vs) == ("own_result", 0.9, "LoRA")
    assert verify.judge(c("86.5", own=True), read("87.2")).delta.value == -0.7
    assert verify.judge(c("88.1", own=True), read("87.2", same="no")).delta is None        # 조건이 다르면 차이를 내지 않는다
    assert verify.judge(c("88.1", own=True), read("높음")).delta is None                    # 숫자가 아니면 내지 않는다
    assert verify.judge(c("88.1", own=True, dataset="GLUE"), read("87.2", dataset="SQuAD")).delta is None


# ---- 근거 없음 ----

def test_all_not_found_is_handoff_without_draft(fake_llm, lib):
    prepare(fake_llm, [claim("DoRA는 71.2다", "DoRA", "71.2"), claim("VeRA는 80.1이다", "VeRA", "80.1")])
    r = verify.run(req(), USER)
    assert r.handoff is True and [c.verdict for c in r.claims] == ["not_found", "not_found"]
    assert r.draft == "" and verify.NOT_FOUND_WARNING in r.warnings and r.source_details == []
    assert [s for _, _, s in fake_llm.structured_calls] == [ClaimExtraction]  # 읽기·초안은 부르지 않는다


def test_no_claims_in_the_manuscript(fake_llm, lib):
    prepare(fake_llm, [])
    r = verify.run(req(), USER)
    assert r.handoff is True and r.claims == [] and verify.NO_CLAIMS_WARNING in r.warnings


def test_value_or_label_missing_means_no_evidence(fake_llm, lib):
    prepare(fake_llm, FIVE[:3], {"LoRA": read("300K", label="S9"), "QLoRA": read(None), "LoRA GLUE": read("87.2", label=None)})
    r = verify.run(req(), USER)
    assert [c.verdict for c in r.claims] == ["not_found"] * 3 and r.handoff is True


# ---- 대상 논문 / 팀 격리 ----

def test_unknown_paper_ids_do_not_widen_the_scope_and_skip_the_llm(fake_llm, lib):
    prepare(fake_llm, FIVE, READS)
    r = verify.run(req(paper_ids=[998, 999]), USER)
    assert r.handoff is True and r.claims == [] and fake_llm.structured_calls == [] and lib == []  # 원고를 LLM에 보내지 않는다


def test_empty_team_index_skips_the_llm(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(verify.store, "paper_chunk_counts", lambda team_id: {})
    prepare(fake_llm, FIVE, READS)
    assert verify.run(req(), USER).handoff is True and fake_llm.structured_calls == []


def test_search_is_limited_to_known_papers_and_the_users_team(fake_llm, lib):
    prepare(fake_llm, FIVE[:1], READS)
    verify.run(req(paper_ids=[41, 999, 41]), CurrentUser(user_id=1, username="u", role="member", team_id=4, team_type="dev", view="dev"))
    assert lib[0]["paper_ids"] == [41] and lib[0]["team_id"] == 4 and lib[0]["sources"] == ["pdf"]
    assert lib[0]["min_score"] == config_rag.MIN_SCORE and lib[0]["k"] == config_rag.VERIFY_EVIDENCE_CHUNKS
    lib.clear()
    prepare(fake_llm, FIVE[:1], READS)
    verify.run(req(), USER)
    assert lib[0]["paper_ids"] is None  # 지정하지 않으면 팀 전체


# ---- 상한 / 실패 ----

def test_claim_cap_warns(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "VERIFY_MAX_CLAIMS", 2)
    prepare(fake_llm, [claim(f"문장 {i}", "LoRA", "0.3M") for i in range(5)], READS)
    r = verify.run(req(), USER)
    assert len(r.claims) == 2 and any("5개라 앞의 2개만" in w for w in r.warnings)


def test_one_failed_read_is_reported_not_hidden(fake_llm, lib):
    prepare(fake_llm, FIVE[:2], {"LoRA": read("300K"), "QLoRA": ApiError(503, "UPSTREAM_TIMEOUT", "x")})
    r = verify.run(req(), USER)
    assert [c.verdict for c in r.claims] == ["match", "not_found"]
    assert r.claims[1].condition == verify.READ_FAILED_CONDITION and any("1개는 확인 중 오류" in w for w in r.warnings)


def test_all_reads_failed_raises_instead_of_handoff(fake_llm, lib):
    err = ApiError(503, "UPSTREAM_TIMEOUT", "x")
    prepare(fake_llm, FIVE[:2], {"LoRA": err, "QLoRA": err})
    with pytest.raises(ApiError) as e:
        verify.run(req(), USER)
    assert e.value.code == "UPSTREAM_TIMEOUT"


def test_extraction_failure_is_an_error(fake_llm, lib):
    def boom(system, user):
        raise ApiError(500, "INTERNAL_ERROR", "x")

    prepare(fake_llm, FIVE)
    fake_llm.state["structured"][ClaimExtraction] = boom
    with pytest.raises(ApiError):
        verify.run(req(), USER)


# ---- 원고 비노출 ----

def test_manuscript_only_goes_to_the_extraction_call(fake_llm, lib):
    prepare(fake_llm, FIVE, READS)
    verify.run(req(), USER)
    with_text = [s.__name__ for _, user, s in fake_llm.structured_calls if SECRET in user]
    assert with_text == ["ClaimExtraction"]  # 읽기·초안 호출에는 원고 전문이 가지 않는다
    system, user, _ = fake_llm.structured_calls[0]
    assert "지시" in system and f"[원고]\n{MANUSCRIPT}" in user  # 원고 안의 지시를 따르지 않도록 알린다


def test_manuscript_is_not_in_logs_or_errors(fake_llm, lib, caplog):
    prepare(fake_llm, FIVE, READS)
    with caplog.at_level(logging.DEBUG):
        verify.run(req(), USER)
    assert SECRET not in caplog.text and "88.1" not in caplog.text
    assert "rag-verify claims=5" in caplog.text
    # 내부 오류도 원고를 담지 않는다
    prepare(fake_llm, FIVE, {"LoRA": RuntimeError(f"내용 {SECRET}"), "QLoRA": read("48GB")})
    with caplog.at_level(logging.DEBUG):
        r = verify.run(req(), USER)
    assert SECRET not in r.model_dump_json() and "mode worker failed: RuntimeError" in caplog.text


# ---- API ----

def test_api_response_keys_and_logs(client, auth, fake_llm, lib, access_log):
    prepare(fake_llm, FIVE, READS)
    r = client.post("/verify", json={"text": MANUSCRIPT, "paper_ids": [41, 42]}, headers={**auth, "X-Request-Id": "req-verify-1"})
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"claims", "draft", "warnings", "sources", "source_details", "needs_review", "handoff", "view", "latency_ms"}
    assert set(data["claims"][0]) == {"sentence", "subject", "metric", "claimed_value", "dataset", "found_value", "condition", "verdict", "labels", "delta"}
    assert data["claims"][4]["delta"] == {"vs": "LoRA", "value": 0.9}
    (rec,) = [x for x in access_log if x["request_id"] == "req-verify-1"]
    assert (rec["path"], rec["status"], rec["team_id"], rec["in_tok"], rec["out_tok"]) == ("/verify", 200, 3, 600, 120)
    assert SECRET not in json.dumps(rec, ensure_ascii=False)


def test_api_requires_login_and_team(client, fake_llm, lib):
    from conftest import make_token
    r = client.post("/verify", json={"text": MANUSCRIPT})
    assert (r.status_code, r.json()["code"]) == (401, "UNAUTHORIZED")
    r = client.post("/verify", json={"text": MANUSCRIPT}, headers={"Authorization": f"Bearer {make_token(team_id=None)}"})
    assert (r.status_code, r.json()["code"]) == (403, "NO_TEAM")
    assert fake_llm.structured_calls == []


@pytest.mark.parametrize("body", [
    {"text": "가" * 9}, {"text": " " * 30}, {"text": SECRET + "가" * 3001}, {"text": f"{SECRET} 원고", "paper_ids": [1.5]},
    {"text": f"{SECRET} 원고", "paper_ids": list(range(51))}, {"text": f"{SECRET} 원고", "view": "all"}, {},
])
def test_api_validation_errors_do_not_echo_the_manuscript(client, auth, fake_llm, body):
    r = client.post("/verify", json=body, headers=auth)
    assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_ERROR")
    assert SECRET not in r.text and fake_llm.structured_calls == []


def test_api_text_length_boundaries(client, auth, fake_llm, lib):
    prepare(fake_llm, [], {})
    assert client.post("/verify", json={"text": "가" * 3000}, headers=auth).status_code == 200
    assert client.post("/verify", json={"text": "가" * 10}, headers=auth).status_code == 200
    assert client.post("/verify", json={"text": "가" * 3001}, headers=auth).status_code == 422


def test_api_other_team_gets_handoff(client, fake_llm, lib, monkeypatch):
    from conftest import make_token
    monkeypatch.setattr(verify.store, "paper_chunk_counts", lambda team_id: {41: 3} if team_id == 3 else {})
    other = {"Authorization": f"Bearer {make_token(team_id=4)}"}
    r = client.post("/verify", json={"text": MANUSCRIPT, "paper_ids": [41]}, headers=other)
    assert r.status_code == 200 and r.json()["handoff"] is True and fake_llm.structured_calls == []


def test_api_not_ready_is_503(client, auth, fake_llm, monkeypatch):
    from app.rag import router_modes
    monkeypatch.setattr(router_modes.store, "readiness", lambda: {"embedder": False})
    r = client.post("/verify", json={"text": MANUSCRIPT}, headers=auth)
    assert (r.status_code, r.json()["code"]) == (503, "NOT_READY")
