#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from statistics import mean


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
SERVICE = re.compile(r"[A-Za-z0-9_.-]{1,80}")
PATH = re.compile(r"(?:/[A-Za-z0-9_./{}:-]{0,160}|<unmatched>)")
PATTERNS = {
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    "API 키": re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    "이메일": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "휴대전화": re.compile(r"\b01[016789][- ]?\d{3,4}[- ]?\d{4}\b"),
    "민감정보 라벨": re.compile(
        r'\b(?:question|prompt|answer|response|stt_text|speech_text|transcript|'
        r'password|api[_-]?key|jwt[_-]?secret|access[_-]?token|authorization)'
        r'\b[\"\s]*[:=]', re.I,
    ),
}
FORBIDDEN_FIELDS = {
    "question", "prompt", "answer", "response", "stttext", "speechtext",
    "transcript", "messages", "content", "context", "password", "apikey",
    "jwtsecret", "accesstoken", "authorization", "username", "displayname",
    "email", "phone", "text", "audio",
}


def decimal_value(value):
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("금액·횟수는 0 이상의 유한한 숫자여야 합니다.") from None
    if not result.is_finite() or result < 0:
        raise ValueError("금액·횟수는 0 이상의 유한한 숫자여야 합니다.")
    return result


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수가 필요합니다.")
    return number


def forbidden_fields(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in FORBIDDEN_FIELDS and item not in (None, ""):
                return True
            if forbidden_fields(item):
                return True
    elif isinstance(value, list):
        return any(forbidden_fields(item) for item in value)
    return False


def reject_constant(value):
    raise ValueError("유효하지 않은 JSON 숫자")


def read_logs(stream, default_service):
    groups = defaultdict(list)
    counts = Counter()
    findings = defaultdict(list)
    for line_number, raw in enumerate(stream, 1):
        counts["lines"] += 1
        line = ANSI.sub("", raw).strip()
        flags = {name for name, pattern in PATTERNS.items() if pattern.search(line)}
        service, body = default_service, line
        prefix, separator, rest = line.partition("|")
        if separator and SERVICE.fullmatch(prefix.strip()):
            service, body = prefix.strip(), rest.strip()
        record = None
        if body.startswith("{"):
            try:
                record = json.loads(body, parse_constant=reject_constant)
                if forbidden_fields(record):
                    flags.add("원문·인증·개인정보 필드")
            except (ValueError, RecursionError):
                counts["invalid_json"] += 1
        else:
            counts["non_json"] += 1
        if flags:
            counts["suspect_lines"] += 1
            for flag in flags:
                counts["suspect_" + flag] += 1
                if len(findings[flag]) < 5:
                    findings[flag].append(line_number)
            continue
        if not isinstance(record, dict):
            continue
        required = {"path", "status", "latency_ms"}
        if not required <= record.keys():
            key = "invalid_request" if required & record.keys() else "non_request_json"
            counts[key] += 1
            continue
        path, status, latency = record["path"], record["status"], record["latency_ms"]
        try:
            valid_latency = type(latency) in (int, float) and math.isfinite(latency) and latency >= 0
        except OverflowError:
            valid_latency = False
        if not (
            isinstance(path, str) and PATH.fullmatch(path)
            and type(status) is int and 100 <= status <= 599
            and valid_latency
        ):
            counts["invalid_request"] += 1
            continue
        tokens = []
        for key in ("in_tok", "out_tok"):
            value = record.get(key)
            if value is not None and (type(value) is not int or value < 0):
                counts["invalid_tokens"] += 1
                value = None
            tokens.append(value)
        groups[(service, path)].append((status, latency, *tokens))
    return groups, counts, findings


def usage_pairs(rows):
    return [(row[2], row[3]) for row in rows if row[2] is not None and row[3] is not None]


def total_cost(pairs, prices):
    if prices is None or not pairs:
        return None
    return sum(
        (Decimal(i) * prices[0] + Decimal(o) * prices[1]) / Decimal(1_000_000)
        for i, o in pairs
    )


def money(value):
    return "미산정" if value is None else f"{value:.8f}"


def report(groups, counts, findings, prices, args):
    print("# 레퍼룸 운영 로그 리포트")
    print(f"\n입력 {counts['lines']}행 / 집계 요청 {sum(map(len, groups.values()))}건")
    print(
        f"비JSON {counts['non_json']}행 / 비요청 JSON {counts['non_request_json']}행 / "
        f"JSON 오류 {counts['invalid_json']}행 / 요청 형식 오류 {counts['invalid_request']}행 / "
        f"토큰 형식 오류 {counts['invalid_tokens']}개 / 민감정보 의심 {counts['suspect_lines']}행"
    )
    print("\n민감정보 의심 행과 요청 형식 오류 행은 통계에서 제외했습니다.")
    print("토큰 평균·비용은 입력/출력 토큰을 모두 측정한 요청만 사용합니다.")
    if prices is None:
        print("LLM_PRICE_IN/LLM_PRICE_OUT 미설정: 비용은 미산정입니다.")
    else:
        print(f"단가: 입력 {prices[0]} / 출력 {prices[1]} USD / 100만 토큰")
    print("\n| 서비스 | 경로 | 요청 수 | 평균/최대/p95 ms | 4xx/5xx % | 평균 입력/출력 tok | 측정 건수 | 측정분 비용 USD | 측정 요청당 USD |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for (service, path), rows in sorted(groups.items()):
        n = len(rows)
        latencies = sorted(row[1] for row in rows)
        p95 = latencies[math.ceil(n * 0.95) - 1]
        four = sum(400 <= row[0] < 500 for row in rows) / n * 100
        five = sum(500 <= row[0] < 600 for row in rows) / n * 100
        pairs = usage_pairs(rows)
        average_tokens = (
            f"{mean(i for i, _ in pairs):.1f}/{mean(o for _, o in pairs):.1f}"
            if pairs else "미측정"
        )
        cost = total_cost(pairs, prices)
        average_cost = cost / len(pairs) if cost is not None else None
        print(
            f"| {service} | {path} | {n} | {mean(latencies):.2f}/{max(latencies):.2f}/{p95:.2f} "
            f"| {four:.1f}/{five:.1f} | {average_tokens} | {len(pairs)}/{n} "
            f"| {money(cost)} | {money(average_cost)} |"
        )
    print("\np95는 정렬 후 ceil(N × 0.95)번째 값입니다. 지연은 모든 상태 코드를 포함합니다.")
    print("측정분 비용은 토큰 미측정 요청·STT/TTS 비용을 포함한 전체 청구액이 아닙니다.")
    print("\n## 월 예상 비용")
    service = args.forecast_service or args.service
    rows = groups.get((service, args.forecast_path), [])
    print(f"대상: {service} / {args.forecast_path}")
    print(
        f"팀원 수: {args.team_members if args.team_members is not None else '미입력'}, "
        f"1인 일 질문 수: {args.daily_questions if args.daily_questions is not None else '미입력'}, "
        f"월 근무일: {args.workdays if args.workdays is not None else '미입력'}"
    )
    print(
        f"월 임베딩 비용 USD: {money(args.embedding_usd)}, "
        f"월 서버 비용 USD: {money(args.server_usd)}"
    )
    pairs = usage_pairs(rows)
    complete = (
        rows and len(pairs) == len(rows) and prices is not None
        and all(value is not None for value in (
            args.team_members, args.daily_questions, args.workdays,
            args.embedding_usd, args.server_usd,
        ))
    )
    if complete:
        per_request = total_cost(pairs, prices) / len(rows)
        planned = Decimal(args.team_members) * args.daily_questions * args.workdays
        monthly = per_request * planned + args.embedding_usd + args.server_usd
        print(f"계획 월 질문 수: {planned}, 월 예상 비용: {money(monthly)} USD")
        print("관찰한 요청 구성과 동일하다는 가정의 추정치입니다. 별도 음성 비용은 포함하지 않습니다.")
    else:
        print("월 예상 비용: 미산정 — 대상 로그·전체 토큰 측정·단가·모든 가정값이 필요합니다.")
    print("\n## 민감정보 패턴 점검")
    if not findings:
        print("의심 패턴 미탐지. 원문·개인정보가 없다는 보증은 아니며 표본을 별도 점검하세요.")
    for flag, lines in sorted(findings.items()):
        print(f"- {flag}: {counts['suspect_' + flag]}행, 예시 행 번호 {', '.join(map(str, lines))}")
    print("원문과 탐지된 실제 값은 리포트에 출력하지 않습니다.")


def main():
    parser = argparse.ArgumentParser(description="공통 요청 JSON 로그의 지연·토큰·비용 집계")
    parser.add_argument("logfile", nargs="?", default="-", help="JSON 로그 파일 또는 표준입력 -")
    parser.add_argument("--service", default="unknown", help="접두사가 없는 로그의 서비스 이름")
    parser.add_argument("--forecast-service", help="월 예상 비용의 대상 서비스")
    parser.add_argument("--forecast-path", default="/rag-query")
    parser.add_argument("--team-members", type=positive_int)
    parser.add_argument("--daily-questions", type=decimal_value)
    parser.add_argument("--workdays", type=positive_int)
    parser.add_argument("--embedding-usd", type=decimal_value)
    parser.add_argument("--server-usd", type=decimal_value)
    args = parser.parse_args()
    if not SERVICE.fullmatch(args.service) or (
        args.forecast_service and not SERVICE.fullmatch(args.forecast_service)
    ) or not PATH.fullmatch(args.forecast_path):
        parser.error("서비스 이름 또는 집계 경로 형식이 올바르지 않습니다.")
    raw_prices = [os.getenv(name, "").strip() for name in ("LLM_PRICE_IN", "LLM_PRICE_OUT")]
    try:
        if any(raw_prices) and not all(raw_prices):
            raise ValueError("LLM_PRICE_IN과 LLM_PRICE_OUT을 함께 설정하세요.")
        prices = tuple(map(decimal_value, raw_prices)) if all(raw_prices) else None
    except ValueError as error:
        parser.error(str(error))
    try:
        if args.logfile == "-":
            groups, counts, findings = read_logs(sys.stdin, args.service)
        else:
            with open(args.logfile, encoding="utf-8") as stream:
                groups, counts, findings = read_logs(stream, args.service)
    except (OSError, UnicodeError):
        print("[FAIL] 로그 입력을 읽을 수 없습니다.", file=sys.stderr)
        return 2
    report(groups, counts, findings, prices, args)
    if not groups:
        print("[FAIL] 집계 가능한 요청 로그가 없습니다.", file=sys.stderr)
    return int(not groups or any(counts[key] for key in (
        "suspect_lines", "invalid_json", "invalid_request", "invalid_tokens",
    )))


if __name__ == "__main__":
    raise SystemExit(main())
