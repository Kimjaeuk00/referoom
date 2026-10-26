# eval/ — 평가 도구 (v0.2 모드 기준)

RAG 서비스를 같은 질문으로 반복 측정한다. 질문은 모드(`tutor` / `prior` / `topic` / `verify`)별로 나뉘고, 모드마다 평가 항목이 다르다.
점수를 새로 만들어 내지 않는다. 측정하지 않은 값은 보고서에 "미측정"으로 적는다.

## 구성

| 파일 | 내용 |
|---|---|
| `questions/rag.jsonl`, `rag_extra.jsonl`, `rag_visual.jsonl` | tutor 질문 49개(일반 29·math 3·거절 17). 모두 `"mode": "tutor"`. 근거 논문이 현재 라이브러리에 없는 질문 20개는 `questions_parked/`로 옮겼다 |
| `questions/modes.jsonl` | prior·topic·verify 샘플 각 3개(`PR`·`TP`·`VF` 접두사). 2026-10-25에 실서버·실제 LLM으로 9개 모두 통과를 확인했다(표본이 작아 정확도 수치로 쓰지 않는다) |
| `run_eval.py` | 질문 검증, 실서버 수집, 오프라인 재집계, 보고서 |
| `mode_checks.py` | prior·topic·verify의 질문 검증·요청 생성·응답 검사(순수 함수) |
| `baseline_bm25.py` | tutor용 키워드 검색 기준선(`--corpus`를 쓸 때만 `rank_bm25` 필요) |
| `results/` | 수집 결과 CSV·보고서(기존 결과는 건드리지 않는다) |

시험: `rag-service`에서 `python -m pytest tests/rag/test_eval_modes.py` (가짜 서버, API 키 불필요).

## v0.1에서 바뀐 점

- 사용자 수준(L1~L3)이 없어졌다. 질문의 `level`은 **이번 질문의 요청 깊이**다(L1 = 더 쉽게, L2 = 기본, L3 = 더 깊게). tutor 질문에는 필수, 다른 모드에서는 생략할 수 있다.
- 질문 유형 `level`을 `depth`로 바꿨다(요청 깊이를 시험하는 질문. 현재 질문 파일에는 없다). 이 유형의 최소 문항 규칙은 없앴다.
- 보고서의 "수준 적합성"은 "요청 깊이 적합성(수동, tutor)"이 됐다. CSV 열 `level_score`는 이름을 유지한다. 음성 서비스의 판정기(`voice-service/evaluation/openai_judge.py`)가 같은 이름의 필드로 판정 양식을 만들기 때문이다. 의미만 요청 깊이 적합성(1~3, 사람 검토 필요)으로 바뀌었다.
- CSV 열 `mode`, `mode_pass`, `mode_detail`이 추가됐다. 열이 달라서 **예전 수집 CSV는 `--review-csv`로 재집계할 수 없다**("Collection schema differs"). 다시 수집한다.
- 자동·사람 판정(정확성·환각·핵심어·요청 깊이·수식)과 BM25는 tutor만 대상이다. 다른 모드는 규칙 검사(`mode_pass`)만 쓰고 판정기를 부르지 않는다.

## 질문 형식

공통 필드: `id`(전체에서 유일), `mode`, `type`, `question`, `expected_answer`(사람이 읽는 기대 설명), `should_refuse`, `level`(위 설명).
`mode`를 생략하면 tutor로 읽는다.

| 모드 | `type` | 추가 필드 | 요청 |
|---|---|---|---|
| tutor | general · math · depth · exception | `key_points`(핵심어 정규식), `evidence`(논문·쪽수. 거절이 아니면 필수) | `POST /rag-query` |
| prior | `prior` | `expected_papers`(표에 있어야 할 논문 제목, 부분 일치), `expected_cells`(`{paper, column, pattern}` 목록, 선택). 거절 질문은 둘 다 없다 | `POST /rag-query` + `mode: "prior"` |
| topic | `topic` | `papers`(제목, 라이브러리에서 하나로 정해져야 함), `min_topics`(기본 1), `n`(기본 3), `hint`(선택) | `POST /topic-suggest` (제목은 `GET /papers`로 id로 바꾼다) |
| verify | `verify` | `expected_claims`(`{contains, verdicts[]}` 목록). `question`이 원고 본문이며 10자 이상 | `POST /verify` |

`should_refuse`는 tutor(= `exception` 유형)와 prior에서만 쓴다. topic·verify는 "근거 없음"을 판정 값(`not_found`)으로 표현한다.

## 모드별 평가 항목

| 모드 | 항목 | 통과 기준 |
|---|---|---|
| tutor | 근거성 | 응답 출처에 정답 논문의 정답 쪽(±1)이 있다 |
| | 거절 | 예외 질문에서 handoff이고 출처가 없다 |
| | 정확성·환각·핵심어 | 판정기 또는 사람 검토 결과가 있을 때만 집계(없으면 미측정) |
| | 요청 깊이 적합성 | 사람 검토(1~3점)만. 깊이별 3건 이상 있어야 평균을 낸다 |
| | 수식·수치 | `needs_review` 배지, 사람 확인 |
| prior | 표에 논문이 있다 | `expected_papers`가 모두 `table` 행 제목에 있다 |
| | 표 칸 정확도 | `expected_cells`의 칸 값이 `pattern`과 맞는다 |
| | 칸의 근거 | 값이 있는 모든 칸의 라벨이 `source_details`에 있다 |
| | 거절 | 근거가 없는 질문은 handoff이고 표·출처가 없다 |
| topic | 후보 수 | `topics` 개수 ≥ `min_topics` |
| | 근거 라벨 | 후보의 `based_on`과 `limitations`의 라벨이 모두 `source_details`에 있다 |
| | 관점 다양성 | 후보끼리 `perspective`가 겹치지 않는다 |
| verify | 판정 정확도 | `contains`가 문장·대상에 들어 있는 주장의 판정이 `verdicts` 중 하나다 |
| | 판정의 근거 | `match`·`mismatch`·`condition_differs`는 라벨이 있고 `source_details`에 있다 |

모든 모드에서 handoff 응답은 기대가 거절인 질문 외에는 실패다. 단 verify는 근거를 하나도 못 찾으면 handoff와 `not_found` 주장을 함께 돌려주므로, 기대 판정이 모두 `not_found`를 허용하는 질문(예: VF03)에서만 handoff를 실패로 보지 않는다. HTTP·응답 구조 오류는 어느 항목의 성공으로도 세지 않는다.
결과 파일에는 질문·답변 원문과 토큰(JWT)을 남기지 않는다. `mode_detail`에는 `papers=2/2;cells=1/1;labels=ok` 같은 개수만 적는다.

## 최소 문항 규칙

전체 20문항 이상, tutor `general` 12·`math` 3·`exception` 3 이상, prior·topic·verify는 각 3 이상. 현재는 tutor 49 + 새 모드 9 = 58문항이다. 호출 수를 줄여 측정할 때는 `subsets/half`(36문항)를 쓴다.
새 모드 샘플 9개는 실서버에서 한 번 돌려 모두 통과했지만(2026-10-25, 시드 라이브러리 기준), 모드당 3개뿐이라 **구조 시험용**이다. 정확도를 말하려면 문항을 늘리고 기대값(논문 제목, 쪽, 판정)을 사람이 확인한다.

## 실행

```bash
cd eval
python run_eval.py --validate-only                      # 질문 구조·문항 수 검사
python run_eval.py --token "$JWT" --timeout 60 --tag mode_v1      # 실서버 수집 (RAG 서버와 토큰 필요, LLM 호출 비용 발생)
python run_eval.py --review-csv results/<날짜>_<태그>.csv --write-review-template review.json   # tutor 판정 양식
python run_eval.py --review-csv results/<날짜>_<태그>.csv --judgments review.json --tag mode_v1_scored   # 재집계(서버 호출 없음)
```

- topic 질문은 라이브러리(`GET /papers`)에서 제목으로 논문 id를 찾는다. 제목이 없거나 둘 이상이면 요청하지 않고 `request_error`로 기록한다.
- 실행은 항상 문항 수 규칙을 채운 질문 폴더 전체를 대상으로 한다(모드만 골라 돌리는 옵션은 아직 없다). 선행연구·주제·검증은 논문·주장 수에 비례해 LLM 호출이 늘어 호출 한 번에 만 토큰 안팎이 든다(A5 실측: 4천~8천). 전체 수집 전에 `--questions-dir`로 문항 수 규칙을 채운 작은 폴더를 따로 만들어 먼저 돌려 보고, 비용은 `--pricing`으로 계산한다.
- 종료 코드: 0 정상, 1 수집·판정이 덜 끝남, 2 입력 오류.

## voice-service 쪽에 요청할 것 (소유가 달라 이 작업에서 고치지 않았다)

- `voice-service/evaluation/rubric.json`의 `instructions.level` 문구가 "요청 수준"을 가리킨다. "요청 깊이(더 쉽게 L1 / 기본 L2 / 더 깊게 L3)에 맞는지"로 바꾸면 보고서와 맞는다. 키 이름(`level`)과 판정 양식의 `level_score` 필드 이름은 바꾸지 않는다(`run_eval.py`가 같은 키를 검사한다).
- `openai_judge.py`는 `question["level"]`을 그대로 읽는다. 판정기는 tutor 질문(요청 깊이가 필수)에만 호출되므로 지금은 문제가 없다. 판정기를 다른 모드에 쓰려면 먼저 이 부분을 `question.get("level")`로 바꿔야 한다.
