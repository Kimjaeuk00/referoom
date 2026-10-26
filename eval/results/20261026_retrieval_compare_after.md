# 비교 질문 검색 측정 (개선 후)

변경: 질문이 라이브러리 논문 2편 이상의 이름을 들면 논문별로 따로 검색해 합친다(`pipeline._with_named_papers`, `paper_names.py`). 이름이 든 논문의 점수 하한은 `NAMED_PAPER_MIN_SCORE=0.50`, 별칭은 `config_rag.PAPER_ALIASES`(수동 표 + 제목 콜론 앞 이름). 범위가 "전체"이고 이름이 2편 이상일 때만 동작한다.
개선 전 기록은 `20261026_retrieval_compare_before.md`.

## 1. 검색 coverage (LLM 호출 없음, `eval/retrieval_coverage.py`)

```
MIN_SCORE=0.55 NAMED_PAPER_MIN_SCORE=0.5 k=5
id   split    전 후  후의 논문별 청크 수 | 후의 상위 논문 분포
C01  design   X  O   {'QLoRA': 2, 'Prefix-Tuning': 3} | {'QLoRA: Efficie': 2, 'Prefix-Tuning:': 3}
C02  design   X  O   {'Prompt Tuning': 3, 'Prefix-Tuning': 2} | {'Prefix-Tuning:': 2, 'The Power of S': 3}
C03  design   X  O   {'LoRA: Low-Rank': 4, 'Parameter-Efficient Transfer': 1} | {'LoRA: Low-Rank': 4, 'Parameter-Effi': 1}
C04  design   X  O   {'QLoRA': 3, 'LoRA: Low-Rank': 2} | {'QLoRA: Efficie': 3, 'LoRA: Low-Rank': 2}
C05  design   X  O   {'Parameter-Efficient Transfer': 2, 'Prefix-Tuning': 3} | {'Prefix-Tuning:': 3, 'Parameter-Effi': 2}
C06  design   X  O   {'LoRA: Low-Rank': 2, 'Prompt Tuning': 3} | {'LoRA: Low-Rank': 2, 'The Power of S': 3}
C07  design   X  O   {'QLoRA': 3, 'Parameter-Efficient Transfer': 2} | {'QLoRA: Efficie': 3, 'Parameter-Effi': 2}
C08  design   X  O   {'RETA-LLM': 3, 'LoRA: Low-Rank': 2} | {'LoRA: Low-Rank': 2, 'RETA-LLM: A Re': 3}
C09  holdout  X  O   {'QLoRA': 2, 'Prefix-Tuning': 3} | {'QLoRA: Efficie': 2, 'Prefix-Tuning:': 3}
C10  holdout  O  O   {'Parameter-Efficient Transfer': 2, 'Prompt Tuning': 3} | {'The Power of S': 3, 'Parameter-Effi': 2}
C11  holdout  X  O   {'LoRA: Low-Rank': 2, 'QLoRA': 3} | {'QLoRA: Efficie': 3, 'LoRA: Low-Rank': 2}
C12  holdout  X  X   {'Prefix-Tuning': 0, 'LoRA: Low-Rank': 4} | {'LoRA: Low-Rank': 4, 'QLoRA: Efficie': 1}
C13  holdout  X  O   {'QLoRA': 2, 'LoRA: Low-Rank': 2, 'Parameter-Efficient Transfer': 1} | {'QLoRA: Efficie': 2, 'LoRA: Low-Rank': 2, 'Parameter-Effi': 1}
C14  holdout  X  O   {'RETA-LLM': 3, 'Prompt Tuning': 2} | {'RETA-LLM: A Re': 3, 'The Power of S': 2}
C15  holdout  X  O   {'Prompt Tuning': 3, 'Parameter-Efficient Transfer': 2} | {'The Power of S': 3, 'Parameter-Effi': 2}
C16  holdout  X  O   {'Parameter-Efficient Transfer': 3, 'LoRA: Low-Rank': 2} | {'LoRA: Low-Rank': 2, 'Parameter-Effi': 3}

design: coverage 전 0/8 → 후 8/8
holdout: coverage 전 1/8 → 후 7/8
전체: coverage 전 1/16 → 후 15/16
```

| split | 전 | 후 |
|---|---|---|
| design (설계에 쓴 8개) | 0/8 | 8/8 |
| holdout (설계가 보지 않은 8개) | 1/8 | **7/8** |
| 전체 | 1/16 | **15/16** |

- **holdout 실패 1건(C12)**: 이름 감지는 맞았지만(Prefix-Tuning, LoRA) Prefix-Tuning의 가장 좋은 문단 점수가 0.495로 하한 0.50에 0.005 모자랐다. 하한은 설계용 8문항에서 정했고, holdout 결과를 보고 값을 바꾸지 않았다(바꾸면 holdout이 설계용이 된다). 하한을 낮출지는 새 문항으로 다시 검증하면서 정해야 한다.

## 2. 단일 논문 질문 검색의 후퇴 여부 (답할 수 있는 32문항, 검색만)

| | 정답 논문·쪽 top5 | 핵심어 완전 포함 |
|---|---|---|
| 적용 전 | 30/32 | 22/32 |
| 적용 후 | 30/32 | 22/32 |

- 검색 결과가 바뀐 문항은 1개뿐이다(이름을 2편 든 문항). 후퇴 없음.

## 3. 실제 답 수준 (LLM 호출, 비교 질문 16개를 1회씩, `RAG_STORE=local`)

| | 거절 | 이름 든 논문 출처가 모두 있는 답 |
|---|---|---|
| 적용 전 | 5/16 | 0/16 |
| 적용 후 | **0/16** | **13/16** |

- 답이 틀렸는지(정확성)는 이 비교 질문에 정답 문항이 없어 **측정하지 않았다**. "두 논문을 근거로 답했는가"만 본 것이다.
- 적용 후에도 두 논문 출처가 모두 있지 않은 3개: C12(위 검색 실패), C03·C16(LoRA와 어댑터 비교 — 이름 감지·검색은 성공했지만 답이 한쪽 논문만 인용). 원인은 확인하지 않았다(미측정).

## 4. 답해야 하는 문항의 거절 (적용 후, 평가 부분집합 18문항 1회씩)

- 거절 0개. (참고: 이전 기준선에서는 V03이 흔들려 거절된 적이 있다.)

## 한계

- 비교 질문 16개는 내가 쓴 문항이고 라이브러리 6편의 쌍으로만 구성했다. 실제 사용자 질문의 분포는 모른다(미측정).
- 별칭 표는 현재 라이브러리 6편 전용이다. 논문이 바뀌면 표에 한 줄을 더해야 하며, 표에 없는 새 논문은 제목 콜론 앞 이름으로만 감지된다.
- 이 측정은 서버를 거치지 않고 같은 파이프라인을 직접 실행한 것이다. 서버 경로의 정식 재수집(`run_eval.py`)은 하지 않았다(비교 질문은 그 문항 세트에 없다).
