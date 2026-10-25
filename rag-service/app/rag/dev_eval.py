"""검색 품질 비교 도구 (개발용). 같은 평가 질문으로 임베딩 모델·저장소 구현을 비교한다.

실행 예 (모델마다 별도 프로세스, 환경변수로 모델·색인 위치를 분리):
  EMBEDDING_MODEL=text-embedding-3-large LOCAL_INDEX_DIR=app/rag/.cache/idx_large \
    python -m app.rag.dev_eval --build

지표: 정답 논문·페이지(±1)가 top-k 안에 있는가(Hit@k, MRR), 정상/예외 질문의 1위 점수 분포.
LLM은 호출하지 않는다 (임베딩 호출만 사용).
"""
import argparse
import json
import re
import sys
from pathlib import Path

from app.rag import config_rag

QUESTIONS = Path(__file__).resolve().parents[3] / "eval" / "questions" / "rag.jsonl"
OUT_DIR = Path(__file__).resolve().parent / ".cache" / "eval"


def first_hit_rank(hits: list, evidences: list[dict], page_tol: int = 1) -> int | None:
    """정답 논문의 정답 페이지(±page_tol)를 처음 포함하는 순위(1부터). 없으면 None."""
    for rank, h in enumerate(hits, start=1):
        for ev in evidences:
            if h.metadata.get("source") == ev["paper"] and any(
                abs(h.metadata.get("page", -99) - p) <= page_tol for p in ev["pages"]
            ):
                return rank
    return None


def answer_rank(hits: list, question: dict) -> int | None:
    """정답 논문의 청크 중 key_points를 모두 담은 첫 순위. 같은 사실이 여러 페이지에 반복되는 긴 논문에서
    페이지 기준(first_hit_rank)이 과소평가되는 것을 보완한다. key_points가 없으면 None."""
    kps = question.get("key_points") or []
    if not kps:
        return None
    paper = question["evidence"]["paper"]
    for rank, h in enumerate(hits, start=1):
        if h.metadata.get("source") == paper and all(re.search(k, h.text, re.I) for k in kps):
            return rank
    return None


def best_threshold(normal: list[float], refused: list[float]) -> tuple[float, int]:
    """정상 질문은 통과, 예외 질문은 거절되는 문항 수가 가장 많은 MIN_SCORE 후보와 그 문항 수."""
    best_t, best_n = 0.0, -1
    for t in sorted(set(normal + refused)):
        n = sum(s >= t for s in normal) + sum(s < t for s in refused)
        if n > best_n:
            best_t, best_n = t, n
    return best_t, best_n


def evaluate(questions: list[dict], search, k: int = 5) -> dict:
    rows, normal_top, refuse_top = [], [], []
    for q in questions:
        hits = search(q["question"], max(k, 10))
        top1 = hits[0].score if hits else 0.0
        if q["should_refuse"]:
            refuse_top.append(top1)
            rows.append({"id": q["id"], "type": q["type"], "top1": top1})
            continue
        rank = first_hit_rank(hits, [q["evidence"], *q.get("evidence_extra", [])])
        arank = answer_rank(hits, q)
        normal_top.append(top1)
        rows.append({"id": q["id"], "type": q["type"], "lang": "en" if q["question"].isascii() else "ko",
                     "top1": top1, "rank": rank, "arank": arank,
                     "top1_paper": hits[0].metadata.get("source", "")[:18] if hits else ""})
    graded = [r for r in rows if "rank" in r]
    n = len(graded)
    thr, thr_n = best_threshold(normal_top, refuse_top)
    return {
        "rows": rows,
        f"hit@1": sum(r["rank"] == 1 for r in graded) / n,
        f"hit@3": sum(bool(r["rank"]) and r["rank"] <= 3 for r in graded) / n,
        f"hit@{k}": sum(bool(r["rank"]) and r["rank"] <= k for r in graded) / n,
        "mrr": sum(1 / r["rank"] for r in graded if r["rank"]) / n,
        "answer_hit@3": sum(bool(r["arank"]) and r["arank"] <= 3 for r in graded) / n,
        f"answer_hit@{k}": sum(bool(r["arank"]) and r["arank"] <= k for r in graded) / n,
        "normal_top1_min": min(normal_top), "normal_top1_mean": sum(normal_top) / n,
        "refuse_top1_max": max(refuse_top) if refuse_top else None,
        "best_min_score": thr, "separated": f"{thr_n}/{len(normal_top) + len(refuse_top)}",
        "k": k,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="이 설정(모델·색인 위치)으로 색인을 새로 만든다")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--team-id", type=int, default=config_rag.LOCAL_TEAM_ID)
    ap.add_argument("--questions", type=Path, nargs="+", default=[QUESTIONS], help="평가 질문 jsonl (여러 개 가능)")
    ap.add_argument("--tag", default="", help="결과 파일명 접미사 (예: mixed)")
    args = ap.parse_args()

    from app.rag.local_store import ingest, store

    if args.build:
        meta = ingest.build_index(args.team_id)
        store.reload()
        sys.stdout.write(f"built chunks={meta['chunk_count']} dim={meta['dim']} model={meta['embedding_model']}\n")

    questions = [json.loads(l) for qp in args.questions for l in qp.read_text(encoding="utf-8").splitlines() if l.strip()]
    res = evaluate(questions, lambda q, k: store.search(args.team_id, ["pdf"], q, k=k), k=args.k)

    w = sys.stdout.write
    w(f"\nmodel={config_rag.EMBEDDING_MODEL} chunk={config_rag.CHUNK_SIZE}/{config_rag.CHUNK_OVERLAP}\n")
    w(f"{'id':4s} {'type':9s} {'lang':4s} {'top1':>6s} {'rank':>5s}  top1 논문\n")
    for r in res["rows"]:
        w(f"{r['id']:4s} {r['type']:9s} {r.get('lang', '-'):4s} {r['top1']:6.3f} {str(r.get('rank', '-')):>5s}  {r.get('top1_paper', '')}\n")
    w(f"\nHit@1={res['hit@1']:.2f} Hit@3={res['hit@3']:.2f} Hit@{args.k}={res[f'hit@{args.k}']:.2f} MRR={res['mrr']:.3f}\n")
    w(f"AnswerHit@3={res['answer_hit@3']:.2f} AnswerHit@{args.k}={res[f'answer_hit@{args.k}']:.2f} (정답 논문 청크가 key_points를 모두 담은 비율)\n")
    w(f"정상 1위 점수 min={res['normal_top1_min']:.3f} mean={res['normal_top1_mean']:.3f} | 예외 1위 점수 max={res['refuse_top1_max']:.3f}\n")
    w(f"점수만으로 가장 잘 갈리는 MIN_SCORE={res['best_min_score']:.3f} → {res['separated']}문항 정상 분류\n")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{config_rag.EMBEDDING_MODEL.replace('/', '_')}_{config_rag.CHUNK_SIZE}{'_' + args.tag if args.tag else ''}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
