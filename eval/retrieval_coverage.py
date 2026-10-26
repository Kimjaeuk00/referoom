"""비교 질문 검색 측정(LLM 호출 없음). 질문이 이름을 든 논문이 모두 상위 k 검색 결과에 들어오는지(coverage)를 잰다.

문항(eval/retrieval/compare.jsonl)에는 정답 쪽 수가 없고 질문이 든 논문의 제목 키(부분 일치, 대소문자 무시)만 있다.
두 가지를 같이 잰다: (전) local_store.store.search(팀, ["pdf","web","annotation"], 질문, k=5) 뒤 MIN_SCORE 미만 제외,
(후) 거기에 파이프라인의 이름 기반 논문별 검색(`pipeline._with_named_papers`)을 더한 현재 튜터 경로. 이 스크립트는 RAG_STORE=local로 import한다.
실행(rag-service 환경): rag-service/.venv/bin/python eval/retrieval_coverage.py [--k 5] [--team-id 3]
"""
import argparse
import collections
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("RAG_STORE", "local")  # 기본값 stub은 가짜 저장소다. pipeline이 실제 색인을 쓰게 import 전에 정한다

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rag-service"))

from app.rag import config_rag, pipeline  # noqa: E402
from app.rag.local_store import store  # noqa: E402
from app.rag.schemas import RagRequest  # noqa: E402

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

    assert pipeline.store.__name__.endswith("local_store.store"), "RAG_STORE=local이어야 실제 색인을 잰다"
    questions = [json.loads(line) for line in args.questions.read_text(encoding="utf-8").splitlines() if line.strip()]
    per_split = collections.defaultdict(lambda: [0, 0, 0])  # [전 통과, 후 통과, 문항 수]
    print(f"MIN_SCORE={config_rag.MIN_SCORE} NAMED_PAPER_MIN_SCORE={config_rag.NAMED_PAPER_MIN_SCORE} k={args.k}")
    print(f"{'id':4s} {'split':8s} 전 후  후의 논문별 청크 수 | 후의 상위 논문 분포")
    for q in questions:
        raw = store.search(args.team_id, SOURCES, q["question"], k=args.k)
        before = [h for h in raw if h.score >= config_rag.MIN_SCORE]
        after = pipeline._with_named_papers(RagRequest(question=q["question"], top_k=args.k), args.team_id, before)
        ok_before = bool(before) and all(covered(q["papers"], before).values())
        counts = covered(q["papers"], after)
        ok_after = bool(after) and all(counts.values())
        row = per_split[q["split"]]
        row[0] += int(ok_before)
        row[1] += int(ok_after)
        row[2] += 1
        spread = collections.Counter(str(h.metadata.get("source", ""))[:14] for h in after)
        print(f"{q['id']:4s} {q['split']:8s} {'O' if ok_before else 'X'}  {'O' if ok_after else 'X'}   {counts} | {dict(spread)}")
    print()
    for split, (b, a, n) in sorted(per_split.items()):
        print(f"{split}: coverage 전 {b}/{n} → 후 {a}/{n}")
    print(f"전체: coverage 전 {sum(v[0] for v in per_split.values())}/{sum(v[2] for v in per_split.values())} → 후 {sum(v[1] for v in per_split.values())}/{sum(v[2] for v in per_split.values())}")


if __name__ == "__main__":
    main()
