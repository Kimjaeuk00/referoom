# 비교 질문 검색 측정 (개선 전)

도구: `eval/retrieval_coverage.py`(LLM 호출 없음, 실제 색인 팀 3), 문항: `eval/retrieval/compare.jsonl`(16개, design 8 / holdout 8). 지표 coverage는 질문이 이름을 든 논문이 **모두** 상위 5개 청크(점수 0.55 이상)에 들어 있는지다. 문항에는 정답 쪽 수가 없다.

## 결과 (그대로 붙임)

```
MIN_SCORE=0.55 k=5
id   split    coverage 논문별 청크 수 (상위 5, MIN_SCORE 이상) | 1위 점수 | 상위 논문 분포
C01  design   X        {'QLoRA': 2, 'Prefix-Tuning': 0} | 0.628 | {'LoRA: Low-Rank': 3, 'QLoRA: Efficie': 2}
C02  design   X        {'Prompt Tuning': 0, 'Prefix-Tuning': 4} | 0.622 | {'Prefix-Tuning:': 4, 'LoRA: Low-Rank': 1}
C03  design   X        {'LoRA: Low-Rank': 5, 'Parameter-Efficient Transfer': 0} | 0.611 | {'LoRA: Low-Rank': 5}
C04  design   X        {'QLoRA': 1, 'LoRA: Low-Rank': 0} | 0.597 | {'QLoRA: Efficie': 1}
C05  design   X        {'Parameter-Efficient Transfer': 0, 'Prefix-Tuning': 3} | 0.646 | {'Prefix-Tuning:': 3, 'LoRA: Low-Rank': 2}
C06  design   X        {'LoRA: Low-Rank': 3, 'Prompt Tuning': 0} | 0.640 | {'QLoRA: Efficie': 2, 'LoRA: Low-Rank': 3}
C07  design   X        {'QLoRA': 4, 'Parameter-Efficient Transfer': 0} | 0.659 | {'QLoRA: Efficie': 4, 'LoRA: Low-Rank': 1}
C08  design   X        {'RETA-LLM': 0, 'LoRA: Low-Rank': 4} | 0.625 | {'QLoRA: Efficie': 1, 'LoRA: Low-Rank': 4}
C09  holdout  X        {'QLoRA': 0, 'Prefix-Tuning': 0} | 0.642 | {'LoRA: Low-Rank': 5}
C10  holdout  O        {'Parameter-Efficient Transfer': 1, 'Prompt Tuning': 2} | 0.640 | {'The Power of S': 2, 'Prefix-Tuning:': 2, 'Parameter-Effi': 1}
C11  holdout  X        {'LoRA: Low-Rank': 0, 'QLoRA': 5} | 0.627 | {'QLoRA: Efficie': 5}
C12  holdout  X        {'Prefix-Tuning': 0, 'LoRA: Low-Rank': 4} | 0.621 | {'LoRA: Low-Rank': 4, 'QLoRA: Efficie': 1}
C13  holdout  X        {'QLoRA': 3, 'LoRA: Low-Rank': 2, 'Parameter-Efficient Transfer': 0} | 0.637 | {'QLoRA: Efficie': 3, 'LoRA: Low-Rank': 2}
C14  holdout  X        {'RETA-LLM': 2, 'Prompt Tuning': 0} | 0.603 | {'RETA-LLM: A Re': 2, 'LoRA: Low-Rank': 1, 'QLoRA: Efficie': 2}
C15  holdout  X        {'Prompt Tuning': 2, 'Parameter-Efficient Transfer': 0} | 0.611 | {'Prefix-Tuning:': 2, 'The Power of S': 2, 'LoRA: Low-Rank': 1}
C16  holdout  X        {'Parameter-Efficient Transfer': 0, 'LoRA: Low-Rank': 5} | 0.617 | {'LoRA: Low-Rank': 5}

design: coverage 0/8
holdout: coverage 1/8
전체: coverage 1/16
```

## 읽기

- coverage는 전체 **1/16**(design 0/8, holdout 1/8)이다. 질문이 두 논문을 들어도 검색은 한 논문(주로 LoRA·QLoRA) 쪽으로 쏠린다. 이전에 메모로 남긴 진단(비교 질문 근거 쏠림)이 수치로 확인됐다.
- 어댑터(`Parameter-Efficient Transfer Learning for NLP`) 논문은 질문이 "어댑터", "Adapter 논문"이라고 분명히 불러도 16개 중 1개(C10)에서만 검색됐다. 한국어 표기뿐 아니라 영문 이름을 쓴 질문(C16)에서도 0이다. 이름이 질문에 있어도 검색이 쓰지 못한다는 뜻이다.
- 1위 점수는 모두 0.60~0.66으로 `MIN_SCORE`(0.55) 위라서, 점수 차단이 아니라 **검색 순위의 쏠림**이 원인이다.
- 한계: 문항은 내가 썼고 16개뿐이다. 논문 쌍의 모양(한국어 표기, 영문, 띄어쓰기 오타, 세 논문 비교)을 섞었지만 실제 사용 질문의 분포는 모른다(미측정). design/holdout 분할은 개선 설계가 holdout을 보지 않게 하려는 것이다.

## V03(표 값 질문)은 검색 문제가 아니라 설정 문제

같은 질문을 `RAG_STORE=local`로 5번씩 직접 돌렸다(`PAGE_IMAGES`는 시험 스크립트에서만 바꿨고 기본값은 그대로 `off`).

| `PAGE_IMAGES` | 정답 수치(73.3·73.7)가 든 답 | 거절 |
|---|---|---|
| off(현재 기본) | 0/5 | 0/5 |
| on | **5/5** | 0/5 |

- 이미지 읽기를 끄면 표의 수치를 못 읽어 답이 틀리고(거절도 아님), 켜면 원본 페이지의 표를 읽어 5번 모두 맞았다.
- 기본값을 켜는 것은 비용(이미지 토큰)·지연이 늘어나는 결정이라 이 작업에서 바꾸지 않았다. 사용자가 정한다.
