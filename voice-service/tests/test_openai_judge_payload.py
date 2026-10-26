"""판정기가 문항의 view 없이도 요청을 만들고, 그 요청에 view가 들어가지 않는지 확인한다(관점 제거 뒤 회귀 시험). 네트워크는 쓰지 않는다."""
import json
from pathlib import Path

import httpx

from evaluation.openai_judge import JudgeError, OpenAIJudge

RUBRIC = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "rubric.json").read_text(encoding="utf-8"))
QUESTION = {"id": "T1", "question": "LoRA란?", "expected_answer": "저랭크 행렬만 학습한다", "key_points": ["저랭크"],
            "should_refuse": False, "level": "L2"}  # view 키가 없다
RESPONSE = {"answer": "저랭크 행렬을 학습합니다 [S1].", "handoff": False, "sources": [], "source_details": []}


def test_payload_is_built_without_view_and_does_not_send_it():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(500)  # 응답 내용은 필요 없다. 요청을 만드는 데까지만 본다.

    client = httpx.Client(transport=httpx.MockTransport(handler))
    judge = OpenAIJudge("offline-test-key", client=client)
    try:
        judge(question=QUESTION, response=RESPONSE, rubric=RUBRIC)
    except JudgeError as error:
        assert error.code == "UPSTREAM_ERROR"  # 예전 버그는 요청을 보내기 전에 INVALID_OUTPUT(KeyError)이었다
    else:
        raise AssertionError("500 응답은 JudgeError여야 한다")
    assert len(seen) == 1
    sent_input = json.loads(seen[0]["input"])
    assert "view" not in sent_input and sent_input["level"] == "L2"
