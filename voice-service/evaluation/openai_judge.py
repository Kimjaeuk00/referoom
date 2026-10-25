"""OpenAI Responses adapter. Never logs keys, prompts, provider errors, or raw output."""

import hashlib
import json
import math
from pathlib import Path
import re
from time import perf_counter

import httpx


DEFAULT_MODEL = "gpt-6-luna"  # User-selected model, verified against the official catalog.
RESPONSES_URL = "https://api.openai.com/v1/responses"
ERROR_CODES = {"UPSTREAM_TIMEOUT", "UPSTREAM_ERROR", "INVALID_OUTPUT", "REFUSED",
               "INCOMPLETE", "MODEL_MISMATCH", "CONTEXT_MISMATCH"}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


class JudgeError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__("판정 모델 응답을 처리하지 못했습니다.")


def load_contexts(path: Path) -> dict:
    """Evaluation-only export; not a new RAG API contract."""
    contexts = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or set(item) != {"id", "response_sha256", "complete", "passages"}:
            raise ValueError("Invalid context export")
        if not isinstance(item["id"], str) or not item["id"].strip() or item["id"] in contexts:
            raise ValueError("Invalid context id")
        if not isinstance(item["response_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["response_sha256"]):
            raise ValueError("Invalid context response fingerprint")
        if type(item["complete"]) is not bool or not isinstance(item["passages"], list):
            raise ValueError("Invalid context completeness")
        if item["complete"] and not item["passages"]:
            raise ValueError("Complete context cannot be empty")
        for passage in item["passages"]:
            if not isinstance(passage, dict) or set(passage) != {"title", "page", "text"}:
                raise ValueError("Invalid context passage")
            if not all(isinstance(passage[key], str) and passage[key].strip() for key in ("title", "text")):
                raise ValueError("Invalid context text")
            if type(passage["page"]) is not int or passage["page"] < 1:
                raise ValueError("Invalid context page")
        contexts[item["id"]] = item
    return contexts


def output_schema(point_count):
    properties = {
        "key_points": {"type": "array", "items": {"type": "string", "enum": ["met", "missing", "contradicted", "unjudgeable"]},
                       "minItems": point_count, "maxItems": point_count},
        "contradiction": {"type": ["boolean", "null"]},
        "refusal_appropriate": {"type": ["boolean", "null"]},
        "fabricated_answer": {"type": ["boolean", "null"]},
        "claims": {"type": "array", "items": {"type": "string", "enum": ["supported", "unsupported", "contradicted", "unjudgeable"]}},
    }
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


class OpenAIJudge:
    def __init__(self, api_key, *, model=DEFAULT_MODEL, contexts=None, client=None,
                 connect_timeout=5, read_timeout=30):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("OPENAI_API_KEY is required")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", model):
            raise ValueError("Explicit API model id is required")
        if not all(isinstance(value, (float, int)) and not isinstance(value, bool)
                   and math.isfinite(value) and value > 0 for value in (connect_timeout, read_timeout)):
            raise ValueError("Positive judge timeouts are required")
        self.model = model
        self.contexts = contexts or {}
        self.last_metadata = {}
        self._api_key = api_key
        self._owns_client = client is None
        # No retries or model fallback. Read is an inactivity limit, not a total deadline.
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            follow_redirects=False, trust_env=False,
        )

    def close(self):
        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __call__(self, *, question, response, rubric):
        self.last_metadata = {}
        started = perf_counter()
        try:
            return self._judge(question, response, rubric)
        except JudgeError as error:
            self.last_metadata["judge_error_code"] = error.code
            raise
        except httpx.TimeoutException:
            self.last_metadata["judge_error_code"] = "UPSTREAM_TIMEOUT"
            raise JudgeError("UPSTREAM_TIMEOUT") from None
        except httpx.RequestError:
            self.last_metadata["judge_error_code"] = "UPSTREAM_ERROR"
            raise JudgeError("UPSTREAM_ERROR") from None
        except (ValueError, TypeError, KeyError):
            self.last_metadata["judge_error_code"] = "INVALID_OUTPUT"
            raise JudgeError("INVALID_OUTPUT") from None
        finally:
            self.last_metadata["judge_latency_ms"] = round((perf_counter() - started) * 1000, 3)

    def _judge(self, question, response, rubric):
        response_hash = fingerprint(response)
        context = self.contexts.get(question["id"])
        if context and context["response_sha256"] != response_hash:
            raise JudgeError("CONTEXT_MISMATCH")
        complete = bool(context and context["complete"])
        passages = context["passages"] if context else []
        point_count = 0 if question["should_refuse"] else len(question["key_points"])
        payload = {
            "model": self.model, "store": False,
            "instructions": "\n".join(rubric["instructions"].values()) + "\n"
                "Return only the specified JSON. key_points follows the supplied order. "
                "For exception questions key_points=[] and judge refusal_appropriate/fabricated_answer. "
                "For ordinary questions refusal_appropriate/fabricated_answer=null. "
                "If context_complete=false, use unjudgeable for claims; never infer completeness. "
                "Do not output reasons, quotes, IDs, hashes, or human scores.",
            "input": json.dumps({
                "question": question["question"], "expected_answer": question["expected_answer"],
                "key_points": [] if question["should_refuse"] else question["key_points"],
                "should_refuse": question["should_refuse"], "level": question["level"],
                "answer": response["answer"], "handoff": response["handoff"],
                "context_complete": complete, "context_passages": passages,
            }, ensure_ascii=False),
            "text": {"format": {"type": "json_schema", "name": "voice_evaluation", "strict": True,
                                "schema": output_schema(point_count)}},
        }
        self.last_metadata["judge_request_sha256"] = fingerprint(payload)
        result = self._client.post(RESPONSES_URL, headers={"Authorization": "Bearer " + self._api_key}, json=payload)
        try:
            if result.status_code != 200:
                raise JudgeError("UPSTREAM_ERROR")
            body = result.json()
            if not isinstance(body, dict):
                raise JudgeError("INVALID_OUTPUT")
            usage = body.get("usage")
            if isinstance(usage, dict):
                for source, target in (("input_tokens", "judge_in_tok"), ("output_tokens", "judge_out_tok")):
                    value = usage.get(source)
                    if type(value) is int and value >= 0:
                        self.last_metadata[target] = value
            resolved = body.get("model")
            if not isinstance(resolved, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", resolved):
                raise JudgeError("MODEL_MISMATCH")
            if resolved != self.model and not resolved.startswith(self.model + "-"):
                raise JudgeError("MODEL_MISMATCH")
            self.last_metadata["judge_resolved_model"] = resolved
            if body.get("status") != "completed" or body.get("error") is not None:
                raise JudgeError("INCOMPLETE")
            texts = []
            if not isinstance(body.get("output"), list):
                raise JudgeError("INVALID_OUTPUT")
            for output in body["output"]:
                if not isinstance(output, dict):
                    raise JudgeError("INVALID_OUTPUT")
                if output.get("type") != "message":
                    continue  # Reasoning items are not JSON output.
                if output.get("role") != "assistant" or output.get("status") != "completed":
                    raise JudgeError("INCOMPLETE")
                if not isinstance(output.get("content"), list):
                    raise JudgeError("INVALID_OUTPUT")
                for content in output["content"]:
                    if not isinstance(content, dict):
                        raise JudgeError("INVALID_OUTPUT")
                    if content.get("type") == "refusal":
                        raise JudgeError("REFUSED")
                    if content.get("type") == "output_text":
                        texts.append(content.get("text"))
            if len(texts) != 1 or not isinstance(texts[0], str):
                raise JudgeError("INVALID_OUTPUT")
            verdict = json.loads(texts[0])
            expected = set(output_schema(point_count)["properties"])
            if not isinstance(verdict, dict) or set(verdict) != expected:
                raise JudgeError("INVALID_OUTPUT")
            points, claims = verdict["key_points"], verdict["claims"]
            if not isinstance(points, list) or len(points) != point_count or not all(
                isinstance(value, str) and value in {"met", "missing", "contradicted", "unjudgeable"} for value in points
            ) or not isinstance(claims, list) or not all(
                isinstance(value, str) and value in {"supported", "unsupported", "contradicted", "unjudgeable"} for value in claims
            ):
                raise JudgeError("INVALID_OUTPUT")
            if not all(verdict[field] is None or type(verdict[field]) is bool for field in (
                "contradiction", "refusal_appropriate", "fabricated_answer",
            )):
                raise JudgeError("INVALID_OUTPUT")
            return {"id": question["id"], "response_sha256": response_hash,
                    **verdict, "context_complete": complete,
                    "context_sha256": fingerprint(passages) if context else None,
                    "human_reviewed": False, "level_score": None, "math_correct": None}
        finally:
            result.close()
