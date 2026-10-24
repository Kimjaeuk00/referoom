"""RAG evaluation collection and measurable checks; no invented quality scores."""

import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
from time import perf_counter

import httpx

# Script-local import; eval is not installed as a Python package.
from baseline_bm25 import BM25Baseline, evidence_hit, load_corpus


EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_RUBRIC = EVAL_DIR.parent / "voice-service" / "evaluation" / "rubric.json"
JUDGE_METADATA_FIELDS = ["judge_in_tok", "judge_out_tok", "judge_latency_ms", "judge_resolved_model",
                         "judge_request_sha256", "judge_error_code"]
FIELDS = ["id", "type", "status", "http_status", "handoff", "needs_review", "review_pass", "grounded",
          "refusal_pass", "bm25_hit_at_k", "latency_ms", "client_latency_ms",
          "in_tok", "out_tok", "level", "view", "dataset_sha256", "response_sha256",
          "rubric_sha256", "judge_model", "judge_status", "accuracy", "hallucinated",
          "refusal_semantic_pass", "human_reviewed", "level_score", "math_correct",
          "context_sha256", "estimated_cost", "cost_currency"] + JUDGE_METADATA_FIELDS


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def load_rubric(path=DEFAULT_RUBRIC):
    rubric = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rubric, dict) or set(rubric) != {"version", "instructions"}:
        raise ValueError("Invalid rubric")
    if not isinstance(rubric["version"], str) or not rubric["version"].strip():
        raise ValueError("Rubric version is required")
    instructions = rubric["instructions"]
    if not isinstance(instructions, dict) or set(instructions) != {
        "accuracy", "faithfulness", "refusal", "level", "math", "safety",
    } or not all(isinstance(value, str) and value.strip() for value in instructions.values()):
        raise ValueError("Rubric instructions are required")
    return rubric


def review_record(item, row):
    return {"id": item["id"], "response_sha256": row["response_sha256"],
            "key_points": ["unjudgeable"] * (0 if item["should_refuse"] else len(item["key_points"])),
            "contradiction": None, "refusal_appropriate": None, "fabricated_answer": None,
            "context_complete": False, "context_sha256": None, "claims": [],
            "human_reviewed": False, "level_score": None, "math_correct": None}


def review_template(rows, questions, rubric):
    return {"dataset_sha256": fingerprint(questions), "rubric_sha256": fingerprint(rubric),
            "judge_model": None,
            "records": [review_record(item, row) for item, row in zip(questions, rows) if row["status"] == "ok"]}


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_judgment(item, row, record):
    template = review_record(item, row)
    if not isinstance(record, dict) or set(record) != set(template):
        raise ValueError("Invalid judgment fields")
    if record["id"] != item["id"] or record["response_sha256"] != row["response_sha256"]:
        raise ValueError("Judgment does not match response")
    points = record["key_points"]
    if not isinstance(points, list) or len(points) != len(template["key_points"]) or not all(
        isinstance(value, str) and value in {"met", "missing", "contradicted", "unjudgeable"} for value in points
    ):
        raise ValueError("Invalid key point judgments")
    for field in ("contradiction", "refusal_appropriate", "fabricated_answer", "math_correct"):
        if record[field] is not None and type(record[field]) is not bool:
            raise ValueError("Invalid boolean judgment")
    if type(record["context_complete"]) is not bool or type(record["human_reviewed"]) is not bool:
        raise ValueError("Invalid review flags")
    if record["context_sha256"] is not None and not _hash(record["context_sha256"]):
        raise ValueError("Invalid context fingerprint")
    if record["context_complete"] and record["context_sha256"] is None:
        raise ValueError("Complete context requires a fingerprint")
    if not isinstance(record["claims"], list) or not all(
        isinstance(value, str) and value in {"supported", "unsupported", "contradicted", "unjudgeable"}
        for value in record["claims"]
    ):
        raise ValueError("Invalid claim judgments")
    score = record["level_score"]
    if score is not None and (type(score) is not int or score not in {1, 2, 3} or not record["human_reviewed"]):
        raise ValueError("Level score requires human review")
    if record["math_correct"] is not None and (item["type"] != "math" or not record["human_reviewed"]):
        raise ValueError("Math assessment requires human review of a math question")


def apply_judgment(item, row, record, model, rubric):
    validate_judgment(item, row, record)
    row.update(rubric_sha256=fingerprint(rubric), judge_model=model,
               human_reviewed=record["human_reviewed"], level_score=record["level_score"],
               math_correct=record["math_correct"], context_sha256=record["context_sha256"])
    if record["math_correct"] is False:
        row["accuracy"] = False
    if model is None:
        # A blank template can carry human level/math review, but cannot pose as an LLM verdict.
        if any(point != "unjudgeable" for point in record["key_points"]) or any(
            record[key] is not None for key in ("contradiction", "refusal_appropriate", "fabricated_answer")
        ) or record["claims"]:
            raise ValueError("Automatic judgments require the fixed judge model identifier")
        row["judge_status"] = "not_configured"
        return
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", model):
        raise ValueError("Invalid judge model identifier")
    row.update(accuracy=None, hallucinated=None, refusal_semantic_pass=None)
    if item["should_refuse"]:
        appropriate, fabricated = record["refusal_appropriate"], record["fabricated_answer"]
        row["hallucinated"] = fabricated
        if not row["refusal_pass"]:
            row["accuracy"] = False
        elif appropriate is not None and fabricated is not None:
            row["accuracy"] = appropriate and not fabricated
        if appropriate is not None and fabricated is not None:
            row["refusal_semantic_pass"] = row["refusal_pass"] and appropriate and not fabricated
    else:
        if row["handoff"]:
            row["accuracy"] = False
        elif record["key_points"] and "unjudgeable" not in record["key_points"] and record["contradiction"] is not None:
            row["accuracy"] = all(value == "met" for value in record["key_points"]) and not record["contradiction"]
        if record["context_complete"] and record["claims"]:
            claims = record["claims"]
            if any(value in {"unsupported", "contradicted"} for value in claims):
                row["hallucinated"] = True
            elif "unjudgeable" not in claims:
                row["hallucinated"] = False
    if record["math_correct"] is False:
        row["accuracy"] = False
    row["judge_status"] = "complete" if row["accuracy"] is not None and row["hallucinated"] is not None else "partial"


def apply_reviews(rows, questions, bundle, rubric):
    if not isinstance(bundle, dict) or set(bundle) != {"dataset_sha256", "rubric_sha256", "judge_model", "records"}:
        raise ValueError("Invalid review bundle")
    if bundle["dataset_sha256"] != fingerprint(questions) or bundle["rubric_sha256"] != fingerprint(rubric):
        raise ValueError("Review dataset or rubric differs")
    if not isinstance(bundle["records"], list):
        raise ValueError("Invalid review records")
    records = {}
    for record in bundle["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or record["id"] in records:
            raise ValueError("Duplicate or invalid review id")
        records[record["id"]] = record
    successful = {row["id"] for row in rows if row["status"] == "ok"}
    if not set(records) <= successful:
        raise ValueError("Unknown or failed response in review")
    # Validate all records before mutating any row.
    by_question = {item["id"]: item for item in questions}
    staged = []
    for row in rows:
        updated = dict(row)
        updated.update(accuracy=False if row["status"] != "ok" else None,
                       hallucinated=None, refusal_semantic_pass=None, human_reviewed=False,
                       level_score=None, math_correct=None, rubric_sha256=None, judge_model=None,
                       context_sha256=None, judge_status="not_configured" if row["status"] == "ok" else "not_applicable")
        updated.update(dict.fromkeys(JUDGE_METADATA_FIELDS))
        if row["id"] in records:
            apply_judgment(by_question[row["id"]], updated, records[row["id"]], bundle["judge_model"], rubric)
        staged.append(updated)
    return staged


def read_collection(path, questions):
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        old_fields = [field for field in FIELDS if field not in JUDGE_METADATA_FIELDS]
        if reader.fieldnames not in (FIELDS, old_fields):
            raise ValueError("Collection schema differs; recollect with this version")
        rows = list(reader)
        if reader.fieldnames == old_fields:
            for row in rows:
                row.update(dict.fromkeys(JUDGE_METADATA_FIELDS, ""))
    if len(rows) != len(questions):
        raise ValueError("Collection question count differs")
    booleans = {"handoff", "needs_review", "review_pass", "grounded", "refusal_pass", "accuracy",
                "hallucinated", "refusal_semantic_pass", "human_reviewed", "math_correct", "bm25_hit_at_k"}
    integers = {"http_status", "in_tok", "out_tok", "level_score", "judge_in_tok", "judge_out_tok"}
    numbers = {"latency_ms", "client_latency_ms", "estimated_cost", "judge_latency_ms"}
    for row, item in zip(rows, questions):
        if set(row) != set(FIELDS) or any(value is None for value in row.values()):
            raise ValueError("Invalid collection row")
        for key, value in list(row.items()):
            if value == "":
                row[key] = None
            elif key in booleans:
                if value not in {"True", "False"}:
                    raise ValueError("Invalid collection boolean")
                row[key] = value == "True"
            elif key in integers:
                row[key] = int(value)
                if row[key] < 0:
                    raise ValueError("Invalid collection integer")
            elif key in numbers:
                row[key] = float(value)
                if not _number(row[key]):
                    raise ValueError("Invalid collection metric")
        if row["id"] != _csv_cell(item["id"]) or row["type"] != item["type"] or row["dataset_sha256"] != fingerprint(questions):
            raise ValueError("Collection does not match questions")
        row["id"] = item["id"]
        if row["level"] != item["level"] or row["view"] != item["view"] or row["status"] not in {
            "ok", "request_error", "http_error", "invalid_response",
        }:
            raise ValueError("Collection request metadata differs")
        if row["status"] == "ok" and (not _hash(row["response_sha256"]) or not _number(row["latency_ms"])):
            raise ValueError("Missing successful response fingerprint or latency")
        # Recompute judgments from supplied reviews rather than trusting edited scores.
        for key in ("accuracy", "hallucinated", "refusal_semantic_pass", "level_score", "math_correct",
                    "rubric_sha256", "judge_model", "context_sha256", "estimated_cost", "cost_currency"):
            row[key] = None
        row["judge_status"] = "not_configured" if row["status"] == "ok" else "not_applicable"
        row["human_reviewed"] = False
        row.update(dict.fromkeys(JUDGE_METADATA_FIELDS))
        if row["status"] != "ok":
            row["accuracy"] = False
    return rows


def load_questions(directory: Path) -> list[dict]:
    questions = []
    seen = set()
    for path in sorted(directory.glob("*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                for field in ("id", "question", "expected_answer"):
                    if not isinstance(item[field], str) or not item[field].strip():
                        raise ValueError
                if item["id"] in seen:
                    raise ValueError
                if item["type"] not in {"general", "math", "level", "exception"}:
                    raise ValueError
                if item["level"] not in {"L1", "L2", "L3"} or item["view"] not in {"dev", "rnd"}:
                    raise ValueError
                if type(item["should_refuse"]) is not bool:
                    raise ValueError
                if (item["type"] == "exception") != item["should_refuse"]:
                    raise ValueError
                if not 2 <= len(item["question"]) <= 1000:
                    raise ValueError
                if not isinstance(item["key_points"], list) or not all(
                    isinstance(point, str) and point.strip() for point in item["key_points"]
                ):
                    raise ValueError
                if not item["should_refuse"] and not item["key_points"]:
                    raise ValueError
                if not item["should_refuse"]:
                    evidence = item["evidence"]
                    if not isinstance(evidence["paper"], str) or not evidence["paper"].strip():
                        raise ValueError
                    if not isinstance(evidence["pages"], list) or not evidence["pages"] or not all(
                        type(page) is int and page >= 1 for page in evidence["pages"]
                    ):
                        raise ValueError
            except (ValueError, TypeError, KeyError):
                raise ValueError(f"Invalid question or duplicate id at {path.name}:{number}") from None
            seen.add(item["id"])
            questions.append(item)
    if not questions:
        raise ValueError("No evaluation questions found; verified questions are required")
    return questions


def dataset_gaps(questions: list[dict]) -> list[str]:
    counts = Counter(item["type"] for item in questions)
    gaps = []
    if len(questions) < 20:
        gaps.append("At least 20 questions are required")
    for kind, minimum in (("general", 12), ("math", 3), ("level", 2), ("exception", 3)):
        if counts[kind] < minimum:
            gaps.append(f"{kind}: at least {minimum} required")
    return gaps


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def valid_response(body) -> bool:
    if not isinstance(body, dict):
        return False
    if not isinstance(body.get("answer"), str) or not body["answer"].strip():
        return False
    if not isinstance(body.get("sources"), list) or not all(isinstance(s, str) for s in body["sources"]):
        return False
    if not isinstance(body.get("source_details"), list) or not all(
        isinstance(source, dict) for source in body["source_details"]
    ):
        return False
    return (
        type(body.get("handoff")) is bool and type(body.get("needs_review")) is bool
        and isinstance(body.get("level"), str) and body["level"] in {"L1", "L2", "L3"}
        and isinstance(body.get("view"), str) and body["view"] in {"dev", "rnd"}
        and _number(body.get("latency_ms"))
    )


def evaluate_questions(questions, client, base_url, token, top_k=5, baseline=None,
                       *, judge=None, judge_model=None, rubric=None):
    rubric = rubric or load_rubric()
    if judge is not None and (not isinstance(judge_model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", judge_model)):
        raise ValueError("Fixed judge model identifier is required")
    if baseline is not None and any(
        item.get("source") != "pdf" or item.get("scope", {"type": "all"}) != {"type": "all"}
        for item in questions
    ):
        raise ValueError("BM25 currently requires source=pdf and scope=all for the same exported corpus")
    rows = []
    for item in questions:
        row = dict.fromkeys(FIELDS)
        row.update(id=item["id"], type=item["type"], status="request_error", level=item["level"], view=item["view"],
                   dataset_sha256=fingerprint(questions), judge_status="not_applicable", accuracy=False,
                   human_reviewed=False)
        request = {"question": item["question"], "level": item["level"],
                   "view": item["view"], "top_k": top_k}
        for field in ("source", "scope"):
            if field in item:
                request[field] = item[field]
        if baseline is not None and not item["should_refuse"]:
            row["bm25_hit_at_k"] = evidence_hit(item["evidence"], baseline.search(item["question"], top_k))
        if item["should_refuse"]:
            row["refusal_pass"] = False
        else:
            row["grounded"] = False
        if item["type"] == "math":
            row["review_pass"] = False
        started = perf_counter()
        try:
            response = client.post(
                base_url.rstrip("/") + "/rag-query", json=request,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.RequestError:
            # Never write exception text: it can contain URLs or credentials.
            row["client_latency_ms"] = round((perf_counter() - started) * 1000)
            rows.append(row)
            continue
        row["client_latency_ms"] = round((perf_counter() - started) * 1000)
        row["http_status"] = response.status_code
        if response.status_code != 200:
            row["status"] = "http_error"
            rows.append(row)
            continue
        try:
            body = response.json()
            valid = valid_response(body)
            if valid:
                valid = body["level"] == item["level"] and body["view"] == item["view"]
        except ValueError:
            valid = False
        if not valid:
            row["status"] = "invalid_response"
            rows.append(row)
            continue
        row.update(status="ok", handoff=body["handoff"], needs_review=body["needs_review"],
                   latency_ms=body["latency_ms"], response_sha256=fingerprint(body),
                   accuracy=None, judge_status="not_configured")
        if item["type"] == "math":
            row["review_pass"] = body["needs_review"]
        for key in ("in_tok", "out_tok"):
            if type(body.get(key)) is int and body[key] >= 0:
                row[key] = body[key]
        if item["should_refuse"]:
            row["refusal_pass"] = body["handoff"] and not body["sources"] and not body["source_details"]
        else:
            row["grounded"] = not body["handoff"] and evidence_hit(item["evidence"], body["source_details"])
        if judge is not None:
            row.update(judge_model=judge_model, rubric_sha256=fingerprint(rubric))
            try:
                record = judge(question=deepcopy(item), response=deepcopy(body), rubric=deepcopy(rubric))
                updated = dict(row)
                apply_judgment(item, updated, record, judge_model, rubric)
                row = updated
            except Exception:
                row["judge_status"] = "error"
            metadata = getattr(judge, "last_metadata", {})
            if isinstance(metadata, dict):
                for field in ("judge_in_tok", "judge_out_tok"):
                    value = metadata.get(field)
                    if type(value) is int and value >= 0:
                        row[field] = value
                value = metadata.get("judge_latency_ms")
                if _number(value):
                    row["judge_latency_ms"] = value
                value = metadata.get("judge_resolved_model")
                if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                    row["judge_resolved_model"] = value
                if _hash(metadata.get("judge_request_sha256")):
                    row["judge_request_sha256"] = metadata["judge_request_sha256"]
                value = metadata.get("judge_error_code")
                if isinstance(value, str) and value in {"UPSTREAM_TIMEOUT", "UPSTREAM_ERROR", "INVALID_OUTPUT", "REFUSED", "INCOMPLETE", "MODEL_MISMATCH", "CONTEXT_MISMATCH"}:
                    row["judge_error_code"] = value
        rows.append(row)
    return rows


def summarize(rows):
    regular = [row for row in rows if row["type"] != "exception"]
    exceptions = [row for row in rows if row["type"] == "exception"]
    latency = [row["latency_ms"] for row in rows if row["status"] == "ok"]
    bm25 = [row["bm25_hit_at_k"] for row in regular if row["bm25_hit_at_k"] is not None]
    math_rows = [row for row in rows if row["type"] == "math"]
    accuracy_known = [row for row in rows if row.get("accuracy") is not None]
    hallucination_known = [row for row in rows if row.get("hallucinated") is not None]
    levels = {}
    for level in ("L1", "L2", "L3"):
        scores = [row["level_score"] for row in rows if row.get("level") == level
                  and row.get("human_reviewed") and row.get("level_score") is not None]
        levels[level] = {"samples": len(scores), "mean": statistics.mean(scores) if scores else None}
    costs = [row for row in rows if row.get("estimated_cost") is not None]
    currencies = {row["cost_currency"] for row in costs}
    judge_usage = [row for row in rows if type(row.get("judge_in_tok")) is int and type(row.get("judge_out_tok")) is int]
    judge_latency = [row["judge_latency_ms"] for row in rows if row.get("judge_latency_ms") is not None]
    return {
        "total": len(rows), "http_ok": sum(row["status"] == "ok" for row in rows),
        "grounded_pass": sum(row["grounded"] is True for row in regular), "grounded_total": len(regular),
        "refusal_pass": sum(row["refusal_pass"] is True for row in exceptions), "refusal_total": len(exceptions),
        "mean_latency_ms": statistics.mean(latency) if latency else None,
        "latency_samples": len(latency), "bm25_pass": sum(bm25), "bm25_total": len(bm25),
        "review_pass": sum(row["review_pass"] is True for row in math_rows), "review_total": len(math_rows),
        "refusal_semantic_known": sum(row.get("refusal_semantic_pass") is not None for row in exceptions),
        "refusal_semantic_pass": sum(row.get("refusal_semantic_pass") is True for row in exceptions),
        "accuracy_pass": sum(row.get("accuracy") is True for row in rows),
        "accuracy_known": len(accuracy_known), "hallucination_count": sum(row.get("hallucinated") is True for row in rows),
        "hallucination_known": len(hallucination_known), "levels": levels,
        "human_reviewed": sum(row.get("human_reviewed") is True for row in rows),
        "math_human_known": sum(row.get("math_correct") is not None for row in math_rows),
        "math_human_pass": sum(row.get("math_correct") is True for row in math_rows),
        "judge_errors": sum(row.get("judge_status") == "error" for row in rows),
        "cost_samples": len(costs), "estimated_cost": sum(row["estimated_cost"] for row in costs) if costs and len(currencies) == 1 else None,
        "cost_currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "judge_usage_samples": len(judge_usage), "judge_input_tokens": sum(row["judge_in_tok"] for row in judge_usage),
        "judge_output_tokens": sum(row["judge_out_tok"] for row in judge_usage),
        "judge_mean_latency_ms": statistics.mean(judge_latency) if judge_latency else None,
    }


def apply_pricing(rows, pricing):
    if not isinstance(pricing, dict) or set(pricing) != {"generation_model", "currency", "input_per_million", "output_per_million"}:
        raise ValueError("Invalid pricing fields")
    if not isinstance(pricing["generation_model"], str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", pricing["generation_model"]):
        raise ValueError("Explicit generation model identifier is required")
    if not isinstance(pricing["currency"], str) or not re.fullmatch(r"[A-Z]{3}", pricing["currency"]):
        raise ValueError("Explicit currency is required")
    if not all(_number(pricing[key]) for key in ("input_per_million", "output_per_million")):
        raise ValueError("Explicit nonnegative prices are required")
    for row in rows:
        if row["status"] == "ok" and all(type(row[key]) is int and row[key] >= 0 for key in ("in_tok", "out_tok")):
            cost = (row["in_tok"] * pricing["input_per_million"] + row["out_tok"] * pricing["output_per_million"]) / 1_000_000
            if not _number(cost):
                raise ValueError("Invalid cost estimate")
            row.update(estimated_cost=cost, cost_currency=pricing["currency"])


def report_paths(output_dir, tag):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tag):
        raise ValueError("Invalid report tag")
    prefix = datetime.now().strftime("%Y%m%d") + "_" + tag
    paths = output_dir / (prefix + ".csv"), output_dir / (prefix + ".md")
    if any(path.exists() for path in paths):
        raise ValueError("Report already exists; use a different tag")
    return paths


def _csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_reports(rows, questions, output_dir: Path, tag: str, *, rubric=None, pricing=None):
    csv_path, md_path = report_paths(output_dir, tag)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    digest = fingerprint(questions)
    with csv_path.open("x", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: _csv_cell(value) for key, value in row.items()} for row in rows)
    mean = summary["mean_latency_ms"]
    latency_text = f"{mean:.1f} ms ({summary['latency_samples']} samples)" if mean is not None else "미측정"
    bm25_text = f"{summary['bm25_pass']}/{summary['bm25_total']}" if summary["bm25_total"] else "미측정 (청크 입력 없음)"
    accuracy = (f"{summary['accuracy_pass']}/{summary['total']} (자동 판정; 사람 검토 {summary['human_reviewed']}건)"
                if summary["accuracy_known"] == len(rows) and rows else
                f"미측정/미완료 (확정 {summary['accuracy_known']}/{summary['total']}, 확인된 정답 {summary['accuracy_pass']})")
    hallucination = (f"{summary['hallucination_count']}건" if rows and summary["hallucination_known"] == len(rows) else
                     f"미측정/미완료 (판정 {summary['hallucination_known']}/{summary['total']}, 확인된 발생 {summary['hallucination_count']}건)")
    level_text = "; ".join(f"{level}: {metrics['samples']}건/평균 {metrics['mean'] if metrics['mean'] is not None else '미측정'}"
                           for level, metrics in summary["levels"].items())
    cost_text = (f"{summary['estimated_cost']:.8f} {summary['cost_currency']} (계측 {summary['cost_samples']}/{summary['total']}, 사용자 제공 단가의 RAG 추정치)"
                 if summary["estimated_cost"] is not None else "미측정 (명시 단가·토큰 필요)")
    rubric_text = f"{rubric['version']} / SHA256 {fingerprint(rubric)}" if rubric else "미지정"
    models = sorted({row['judge_model'] for row in rows if row.get('judge_model')})
    resolved_models = sorted({row['judge_resolved_model'] for row in rows if row.get('judge_resolved_model')})
    judge_usage_text = (f"입력 {summary['judge_input_tokens']} / 출력 {summary['judge_output_tokens']} ({summary['judge_usage_samples']}건)"
                        if summary["judge_usage_samples"] else "미측정")
    md_path.write_text(
        f"# 평가 수집 결과: {tag}\n\n"
        f"- 문항 수: {summary['total']}\n"
        f"- 정상 응답: {summary['http_ok']}/{summary['total']}\n"
        f"- 근거성: {summary['grounded_pass']}/{summary['grounded_total']} (논문·페이지 ±1)\n"
        f"- 예외 거절: {summary['refusal_pass']}/{summary['refusal_total']}\n"
        f"- 예외 본문 의미 검사: 통과 {summary['refusal_semantic_pass']}, 판정 {summary['refusal_semantic_known']}/{summary['refusal_total']}\n"
        f"- 수식·수치 검토 배지: {summary['review_pass']}/{summary['review_total']}\n"
        f"- 평균 서버 지연: {latency_text}\n"
        f"- BM25 근거 Hit@k: {bm25_text}\n"
        "- RAG 검색 Recall@k: 미측정 (전체 검색 결과 필요)\n"
        f"- 정확성: {accuracy}\n"
        f"- 환각(일반·예외, 문항 중복 합산 없음): {hallucination}\n"
        f"- 수준 적합성(수동): {level_text} / 각 수준 최소 3건 필요\n"
        f"- 수식 사람 확인: {summary['math_human_known']}/{summary['review_total']} (정확 {summary['math_human_pass']})\n"
        f"- 판정기 오류: {summary['judge_errors']}건\n"
        f"- RAG 추정 비용: {cost_text}\n"
        f"- 판정 루브릭: {rubric_text}\n"
        f"- 판정 모델: {', '.join(models) if models else '미지정'}\n"
        f"- 판정 API 반환 모델: {', '.join(resolved_models) if resolved_models else '미측정'}\n"
        f"- 판정 API 토큰(RAG와 별도): {judge_usage_text}\n"
        f"- 판정 처리 평균 지연 ms(통신·로컬검증 포함, RAG와 별도): {summary['judge_mean_latency_ms'] if summary['judge_mean_latency_ms'] is not None else '미측정'}\n"
        f"- 가격 설정 SHA256: {fingerprint(pricing) if pricing else '미지정'}\n"
        f"- 비용 모델(사용자 선언): {pricing['generation_model'] if pricing else '미지정'}\n"
        "- 배포 판단: 보류 — 전체 품질 평가가 완료되지 않음\n"
        f"- 평가셋 SHA256: {digest}\n\n"
        "HTTP/응답 실패는 근거성·예외 거절의 성공으로 집계하지 않습니다. "
        "최종 인용 출처를 전체 검색 결과로 간주하지 않습니다. "
        "질문·답변 원문 및 토큰(JWT)은 이 결과 파일에 저장하지 않습니다.\n",
        encoding="utf-8",
    )
    return csv_path, md_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions-dir", type=Path, default=EVAL_DIR / "questions")
    parser.add_argument("--output-dir", type=Path, default=EVAL_DIR / "results")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--token")
    parser.add_argument("--tag", default="baseline")
    parser.add_argument("--timeout", type=float, help="Live HTTP timeout in seconds; choose explicitly")
    parser.add_argument("--top-k", type=int, choices=range(1, 11), default=5)
    parser.add_argument("--corpus", type=Path, help="Optional exported text/metadata JSONL for BM25")
    parser.add_argument("--team-id", type=int, help="Required with --corpus")
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC)
    parser.add_argument("--review-csv", type=Path, help="Rescore a collection without calling RAG")
    reviews = parser.add_mutually_exclusive_group()
    reviews.add_argument("--judgments", type=Path, help="Bound structured judge/human results JSON")
    reviews.add_argument("--write-review-template", type=Path, help="Export a blank template from --review-csv")
    parser.add_argument("--pricing", type=Path, help="Explicit generation model/currency/per-million prices JSON")
    parser.add_argument("--judge-openai", action="store_true", help="Call the user-selected OpenAI judge (paid)")
    parser.add_argument("--judge-model", help="Override EVAL_JUDGE_MODEL; default is user-selected gpt-6-luna")
    parser.add_argument("--judge-contexts", type=Path, help="Evaluation-only JSONL of actual generation context")
    args = parser.parse_args(argv)
    try:
        questions = load_questions(args.questions_dir)
        gaps = dataset_gaps(questions)
        if gaps:
            raise ValueError("; ".join(gaps))
        if args.validate_only:
            print(f"Question structure/counts OK: {len(questions)}. Evidence, comparisons, and language mix require manual review.")
            return 0
        if (args.judge_model or args.judge_contexts) and not args.judge_openai:
            raise ValueError("Judge options require --judge-openai")
        if args.judge_openai and args.review_csv:
            raise ValueError("OpenAI judging is a live collection mode")
        rubric = load_rubric(args.rubric)
        pricing = json.loads(args.pricing.read_text(encoding="utf-8")) if args.pricing else None
        if pricing is not None:
            apply_pricing([], pricing)
        if args.review_csv:
            rows = read_collection(args.review_csv, questions)
            if args.write_review_template:
                template = review_template(rows, questions, rubric)
                args.write_review_template.parent.mkdir(parents=True, exist_ok=True)
                with args.write_review_template.open("x", encoding="utf-8") as output:
                    json.dump(template, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                print(args.write_review_template)
                return 0
            if not args.judgments:
                raise ValueError("--judgments is required when rescoring")
            report_paths(args.output_dir, args.tag)
            bundle = json.loads(args.judgments.read_text(encoding="utf-8"))
            rows = apply_reviews(rows, questions, bundle, rubric)
            if pricing is not None:
                apply_pricing(rows, pricing)
            for path in write_reports(rows, questions, args.output_dir, args.tag, rubric=rubric, pricing=pricing):
                print(path)
            return 1 if any(row["status"] != "ok" or row.get("accuracy") is None or row.get("hallucinated") is None for row in rows) else 0
        if args.judgments or args.write_review_template:
            raise ValueError("Review inputs require --review-csv")
        if not args.token or not args.token.strip():
            raise ValueError("--token is required for live evaluation")
        if args.timeout is None or not _number(args.timeout) or args.timeout == 0:
            raise ValueError("Specify a positive --timeout for live evaluation")
        report_paths(args.output_dir, args.tag)
        baseline = None
        if args.corpus:
            if args.team_id is None:
                raise ValueError("--team-id is required with --corpus")
            baseline = BM25Baseline(load_corpus(args.corpus, args.team_id))
        with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
            if args.judge_openai:
                service_dir = EVAL_DIR.parent / "voice-service"
                if str(service_dir) not in sys.path:
                    sys.path.insert(0, str(service_dir))
                from dotenv import load_dotenv
                from evaluation.openai_judge import DEFAULT_MODEL, OpenAIJudge, load_contexts
                load_dotenv(service_dir / ".env")
                load_dotenv(service_dir / "app" / ".env")
                contexts = load_contexts(args.judge_contexts) if args.judge_contexts else {}
                if not set(contexts) <= {item["id"] for item in questions}:
                    raise ValueError("Unknown generation context id")
                with OpenAIJudge(
                    os.getenv("OPENAI_API_KEY"), model=args.judge_model or os.getenv("EVAL_JUDGE_MODEL", DEFAULT_MODEL),
                    contexts=contexts, connect_timeout=float(os.getenv("EVAL_JUDGE_CONNECT_TIMEOUT", "5")),
                    read_timeout=float(os.getenv("EVAL_JUDGE_READ_TIMEOUT", "30")),
                ) as judge:
                    rows = evaluate_questions(questions, client, args.base_url, args.token, args.top_k, baseline,
                                               rubric=rubric, judge=judge, judge_model=judge.model)
            else:
                rows = evaluate_questions(questions, client, args.base_url, args.token, args.top_k, baseline, rubric=rubric)
        if pricing is not None:
            apply_pricing(rows, pricing)
        for path in write_reports(rows, questions, args.output_dir, args.tag, rubric=rubric, pricing=pricing):
            print(path)
        return 1 if any(row["status"] != "ok" or (args.judge_openai and row.get("judge_status") != "complete") for row in rows) else 0
    except (ValueError, OSError):
        # Validation errors originate locally, but filesystem errors can expose
        # private paths. Keep CLI diagnostics bounded to known input checks.
        print("Evaluation cannot run: check verified question files, unique ids, required counts, "
              "token/timeout, corpus/team selection, rubric/review/pricing, and output tag/path.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
