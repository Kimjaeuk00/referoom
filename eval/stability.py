"""검증 모드(/verify) 판정 안정성 반복 시험: 같은 원고 문장을 여러 번 보내 판정이 흔들리는 비율을 잰다.

정답은 보지 않는다. 문장(질문)마다 주장 위치별로 판정 값 분포와 최빈값 비율(일치율)만 낸다.
실제 LLM을 호출하므로 비용이 든다. 호출 수를 먼저 알리고 --yes 없이는 진행하지 않으며, --max-calls를 넘으면 시작하지 않는다.
결과에는 원고 원문·주장 문장을 남기지 않고 질문 id와 판정 분포만 쓴다.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import httpx

import mode_checks

EVAL_DIR = Path(__file__).resolve().parent
EXPECTED_INPUT_TOKENS = 5_700  # /verify 한 번의 실측 평균 입력 토큰(5.7k). 호출 전 비용 안내용
ERROR = "error"  # 응답을 받지 못했거나 200이 아닌 호출


def stability(verdicts: dict[str, list[str]]) -> dict[str, dict]:
    """키(질문 id#주장 위치)별 판정 목록 → 분포와 최빈값 비율. 최빈값이 같은 수로 겹치면 이름순으로 앞선 값을 최빈값으로 쓴다."""
    result = {}
    for key, values in verdicts.items():
        counts = Counter(values)
        top = min(counts, key=lambda v: (-counts[v], v))
        result[key] = {"n": len(values), "distribution": dict(sorted(counts.items())),
                       "mode": top, "agreement": round(counts[top] / len(values), 3)}
    return result


def summarize(per_call: dict[str, list[list[str]]]) -> dict:
    """질문 id → 호출마다의 주장별 판정 목록(호출 실패는 None). 주장 위치별 안정성과 주장 수 분포를 만든다."""
    claims, counts, errors = {}, {}, {}
    for qid, calls in per_call.items():
        errors[qid] = sum(c is None for c in calls)
        counts[qid] = dict(sorted(Counter(len(c) for c in calls if c is not None).items()))
        for call in calls:
            for i, verdict in enumerate(call or []):
                claims.setdefault(f"{qid}#{i + 1}", []).append(verdict)
    return {"claims": stability(claims), "claim_counts": counts, "errors": errors}


def run_once(client, base_url: str, token: str, item: dict) -> list[str] | None:
    path, body = mode_checks.build_request(item, top_k=5)
    try:
        response = client.post(base_url.rstrip("/") + path, json=body, headers={"Authorization": f"Bearer {token}"})
        data = response.json() if response.status_code == 200 else None
    except (httpx.RequestError, ValueError):
        return None
    claims = data.get("claims") if isinstance(data, dict) else None
    if not isinstance(claims, list):
        return None
    return [c.get("verdict") if isinstance(c, dict) and c.get("verdict") in mode_checks.VERDICTS else ERROR for c in claims]


def collect(items: list[dict], repeat: int, client, base_url: str, token: str) -> dict[str, list[list[str]]]:
    return {item["id"]: [run_once(client, base_url, token, item) for _ in range(repeat)] for item in items}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=Path, default=EVAL_DIR / "questions" / "modes.jsonl")
    parser.add_argument("--ids", nargs="+", help="시험할 verify 질문 id (기본: 파일의 verify 전부)")
    parser.add_argument("--repeat", type=int, required=True, help="질문마다 반복 횟수")
    parser.add_argument("--max-calls", type=int, required=True, help="전체 호출 수 상한. 넘으면 시작하지 않는다")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--token", required=True)
    parser.add_argument("--timeout", type=float, required=True, help="HTTP 제한 시간(초)")
    parser.add_argument("--tag", default="stability")
    parser.add_argument("--output-dir", type=Path, default=EVAL_DIR / "results")
    parser.add_argument("--yes", action="store_true", help="비용 안내를 보고 실제 호출을 진행한다")
    args = parser.parse_args(argv)

    items = [json.loads(line) for line in args.questions.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = [q for q in items if q.get("mode") == "verify" and (args.ids is None or q["id"] in args.ids)]
    calls = len(items) * args.repeat
    if not items or args.repeat < 1:
        print("시험할 verify 질문이 없거나 반복 횟수가 1보다 작습니다.", file=sys.stderr)
        return 2
    print(f"호출 {calls}회 (질문 {len(items)}개 x {args.repeat}회), 예상 입력 약 {EXPECTED_INPUT_TOKENS // 1000}.{EXPECTED_INPUT_TOKENS % 1000 // 100}k x {calls} = {EXPECTED_INPUT_TOKENS * calls:,} 토큰")
    if calls > args.max_calls:
        print(f"호출 수가 상한({args.max_calls})을 넘어 시작하지 않습니다.", file=sys.stderr)
        return 2
    if not args.yes:
        print("--yes를 주어야 실제로 호출합니다.", file=sys.stderr)
        return 2

    with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
        report = summarize(collect(items, args.repeat, client, args.base_url, args.token))
    report.update(repeat=args.repeat, calls=calls)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / f"{args.tag}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key, row in report["claims"].items():
        print(f"{key}: 일치율 {row['agreement']:.0%} {row['distribution']}")
    print(f"주장 수 분포 {report['claim_counts']}, 실패 {report['errors']}\n결과: {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
