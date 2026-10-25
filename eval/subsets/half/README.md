# 절반 평가 부분집합 (C단계 기준선용)

`questions/`의 78문항에서 호출 수를 줄이려고 고른 45문항이다. 문항을 골라서 뽑지 않고 규칙으로 정했다.

- tutor: 파일 안에서 같은 `type`끼리 순서대로 세어 0번째, 2번째, 4번째…만 둔다(general 28, exception 5, math 3 = 36).
- prior·topic·verify: 샘플 9개를 모두 둔다.
- 실행: `python run_eval.py --questions-dir subsets/half --token "$EVAL_TOKEN" --timeout 60 --tag <이름>`
- 전후 비교(C4)도 같은 폴더로 돌려야 문항 해시가 같다.
