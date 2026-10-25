# 절반 평가 부분집합 (C단계 기준선용)

`questions/`(58문항)에서 호출 수를 줄이려고 규칙으로 고른 부분집합이다.

- tutor `general`·`exception`: 파일 안에서 같은 `type`끼리 순서대로 세어 0번째, 2번째, 4번째…만 둔다.
- tutor `math`(3개)와 prior·topic·verify 샘플: 전부 둔다.
- 실행: `python run_eval.py --questions-dir subsets/half --token "$EVAL_TOKEN" --timeout 60 --tag <이름>`
- 전후 비교도 같은 폴더로 돌려야 문항 해시가 같다.
- 2026-10-26: 라이브러리에 없는 논문을 묻던 문항을 정리하면서 다시 만들었다(이전 45문항 버전의 결과는 `results/20261026_baseline_half*`에 기록으로만 남아 있다).
