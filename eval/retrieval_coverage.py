"""비교 질문 검색 측정(LLM 호출 없음). 질문이 이름을 든 논문이 모두 상위 k 검색 결과에 들어오는지(coverage)를 잰다.

문항(eval/retrieval/compare.jsonl)에는 정답 쪽 수가 없고 질문이 든 논문의 제목 키(부분 일치, 대소문자 무시)만 있다.
검색은 파이프라인 튜터 경로와 같게 부른다: local_store.store.search(팀, ["pdf","web","annotation"], 질문, k=5) 뒤 MIN_SCORE 미만 제외.
실행(rag-service 환경): rag-service/.venv/bin/python eval/retrieval_coverage.py [--k 5] [--team-id 3]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag-service"))

from app.rag import config_rag  # noqa: E402
from app.rag.local_store import store  # noqa: E402

SOURCES = ["pdf", "web", "annotation"]


def covered(papers: list[str], hits: list) -> dict[str, int]:
    """논문 키별로 상위 hits 중 그 논문의 청크 개수."""
    return {key: sum(key.lower() in str(h.metadata.get("source", "")).lower() for h in hits) for key in papers}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--team-id", type=int, default=config_rag.LOCAL_TEAM_ID)
    ap.add_argument("--questions", type=Path, default=ROOT / "eval" / "retrieval" / "compare.jsonl")
    args = ap.parse_args()

    questions = [json.loads(line) for line in args.questions.read_text(encoding="utf-8").splitlines() if line.strip()]
    per_split = collections.defaultdict(lambda: [0, 0])
    print(f"MIN_SCORE={config_rag.MIN_SCORE} k={args.k}")
    print(f"{'id':4s} {'split':8s} {'coverage':8s} 논문별 청크 수 (상위 {args.k}, MIN_SCORE 이상) | 1위 점수 | 상위 논문 분포")
    for q in questions:
        raw = store.search(args.team_id, SOURCES, q["question"], k=args.k)
        hits = [h for h in raw if h.score >= config_rag.MIN_SCORE]
        counts = covered(q["papers"], hits)
        ok = bool(hits) and all(counts.values())
        per_split[q["split"]][0] += int(ok)
        per_split[q["split"]][1] += 1
        spread = collections.Counter(str(h.metadata.get("source", ""))[:14] for h in hits)
        top1 = raw[0].score if raw else 0.0
        print(f"{q['id']:4s} {q['split']:8s} {'O' if ok else 'X':8s} {counts} | {top1:.3f} | {dict(spread)}")
    print()
    total_ok = sum(v[0] for v in per_split.values())
    total = sum(v[1] for v in per_split.values())
    for split, (ok, n) in sorted(per_split.items()):
        print(f"{split}: coverage {ok}/{n}")
    print(f"전체: coverage {total_ok}/{total}")


if __name__ == "__main__":
    main()
