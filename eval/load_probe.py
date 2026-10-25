"""동시 요청 지연 측정: 같은 경로를 동시 수 1·4·8로 N회씩 불러 평균/최대/p95(ms)만 낸다. 정확성은 보지 않는다.

기본은 LLM을 부르지 않는 경로만 쓴다: /health, /papers, 그리고 서재에 없는 주제를 묻는 /rag-query(근거 점수가 낮아 LLM 없이 '찾을 수 없음'으로 답하지만
질문 임베딩과 검색은 한다. 임베딩이 동기 호출이라 동시 요청에서 느려지는지 보는 경로다).
LLM 경로(/rag-query 실제 답변)는 --llm과 --yes를 모두 줘야 하고, 동시 3개 1회만 부른다.
"""
import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from statistics import mean

import httpx

EVAL_DIR = Path(__file__).resolve().parent
LEVELS = (1, 4, 8)
LLM_CONCURRENCY = 3
OUT_OF_SCOPE = "중세 유럽 농업 제도의 변화는 어떻게 이루어졌나요?"  # modes.jsonl PR03과 같은 계열: 서재에 없는 주제라 LLM 없이 끝난다
IN_SCOPE = "LoRA는 어떤 파라미터를 학습하나요?"

PATHS = {
    "health": ("GET", "/health", None),
    "papers": ("GET", "/papers", None),
    "rag_no_llm": ("POST", "/rag-query", {"question": OUT_OF_SCOPE}),
}
LLM_PATH = ("POST", "/rag-query", {"question": IN_SCOPE})


def aggregate(latencies_ms: list[float]) -> dict:
    """평균/최대/p95. p95는 scripts/ops_report.py와 같은 방식(정렬 후 ceil(N × 0.95)번째)."""
    ordered = sorted(latencies_ms)
    n = len(ordered)
    return {"n": n, "mean": round(mean(ordered), 1), "max": round(ordered[-1], 1), "p95": round(ordered[math.ceil(n * 0.95) - 1], 1)}


async def run_level(client: httpx.AsyncClient, route: tuple, concurrency: int, total: int, headers: dict) -> dict:
    method, path, body = route
    gate = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    statuses: dict[int, int] = {}

    async def one():
        async with gate:
            started = time.perf_counter()
            try:
                response = await client.request(method, path, json=body, headers=headers)
                status = response.status_code
            except httpx.RequestError:
                status = 0
            latencies.append((time.perf_counter() - started) * 1000)
            statuses[status] = statuses.get(status, 0) + 1

    await asyncio.gather(*(one() for _ in range(total)))
    return {"concurrency": concurrency, **aggregate(latencies), "statuses": dict(sorted(statuses.items()))}


def table(name: str, rows: list[dict]) -> str:
    lines = [f"\n### {name}", "| 동시 수 | 요청 수 | 평균 ms | 최대 ms | p95 ms | 상태 코드 |", "|---:|---:|---:|---:|---:|---|"]
    lines += [f"| {r['concurrency']} | {r['n']} | {r['mean']} | {r['max']} | {r['p95']} | {r['statuses']} |" for r in rows]
    return "\n".join(lines)


async def probe(args) -> dict:
    headers = {"Authorization": f"Bearer {args.token}"}
    report = {}
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=args.timeout, follow_redirects=False) as client:
        for name in args.paths:
            await run_level(client, PATHS[name], 1, 1, headers)  # 첫 호출의 로딩 비용은 빼려고 한 번 데운다
            report[name] = [await run_level(client, PATHS[name], c, args.requests, headers) for c in LEVELS]
            print(table(name, report[name]))
        if args.llm:
            report["rag_llm"] = [await run_level(client, LLM_PATH, LLM_CONCURRENCY, LLM_CONCURRENCY, headers)]
            print(table(f"rag_llm (동시 {LLM_CONCURRENCY}개 1회)", report["rag_llm"]))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", nargs="+", choices=list(PATHS), default=list(PATHS))
    parser.add_argument("--requests", type=int, default=16, help="동시 수마다 보내는 요청 수")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--token", required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--llm", action="store_true", help="LLM 경로를 동시 3개 1회 부른다(유료). --yes도 필요하다")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--output", type=Path, help="결과 JSON 파일(수치만)")
    args = parser.parse_args(argv)
    if args.requests < 1:
        print("--requests는 1 이상이어야 합니다.", file=sys.stderr)
        return 2
    if args.llm and not args.yes:
        print(f"--llm은 LLM을 {LLM_CONCURRENCY}번 부릅니다(유료). --yes를 함께 주어야 진행합니다.", file=sys.stderr)
        return 2
    report = asyncio.run(probe(args))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
