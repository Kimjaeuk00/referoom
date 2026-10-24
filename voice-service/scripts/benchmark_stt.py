"""Local ten-recording prompt comparison; never stores reference/transcribed text."""

import argparse
import csv
from datetime import datetime
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import statistics
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import unicodedata

SERVICE_DIR = Path(__file__).resolve().parents[1]
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

from app.services import stt_service
from app.utils.audio_utils import MAX_AUDIO_BYTES, SUPPORTED_EXTENSIONS, prepare_audio


FIELDS = ["id", "phase", "status", "char_edits", "reference_chars", "cer",
          "latency_ms", "duration_s", "audio_sha256"]


def normalize(text: str) -> str:
    """Case-fold NFKC text, ignoring spacing and punctuation for simple CER."""
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum())


def edit_distance(reference: str, hypothesis: str) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def audio_digest(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_AUDIO_BYTES:
                raise ValueError("Audio exceeds 10MB")
            digest.update(chunk)
    if not total:
        raise ValueError("Empty audio")
    return digest.hexdigest()


def load_samples(manifest: Path) -> list[dict]:
    samples = []
    seen_ids, seen_audio = set(), set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", item["id"],
        ):
            raise ValueError("Use unique ASCII sample ids")
        if not isinstance(item.get("reference"), str) or not normalize(item["reference"]):
            raise ValueError("Reference sentence is required")
        if not isinstance(item.get("audio"), str) or not item["audio"].strip():
            raise ValueError("Audio path is required")
        language = item.get("language", "ko")
        if not isinstance(language, str) or language not in {"ko", "en", "auto"}:
            raise ValueError("Invalid language")
        path = Path(item["audio"])
        path = (manifest.parent / path).resolve() if not path.is_absolute() else path.resolve()
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise ValueError("Unsupported audio extension")
        digest = audio_digest(path)
        if item["id"] in seen_ids or digest in seen_audio:
            raise ValueError("Duplicate sample id or recording")
        seen_ids.add(item["id"])
        seen_audio.add(digest)
        samples.append({"id": item["id"], "audio": path, "reference": item["reference"],
                        "language": language, "audio_sha256": digest})
    if len(samples) != 10:
        raise ValueError("Exactly ten distinct recordings are required")
    return samples


def prepare_samples(samples: list[dict], directory: Path) -> list[dict]:
    prepared = []
    for index, sample in enumerate(samples):
        target = directory / str(index)
        target.mkdir()
        with sample["audio"].open("rb") as source:
            wav, duration = prepare_audio(source, sample["audio"].name, target)
        copied = target / ("input" + sample["audio"].suffix.lower())
        if audio_digest(copied) != sample["audio_sha256"]:
            raise ValueError("Recording changed after validation")
        prepared.append({**sample, "wav": wav, "duration_s": duration})
    return prepared


def measure(prepared: list[dict]) -> list[dict]:
    rows = []
    for index, sample in enumerate(prepared):
        reference = normalize(sample["reference"])
        phases = [("before", None), ("after", stt_service.INITIAL_PROMPT)]
        # Alternate order to reduce systematic first-inference bias.
        if index % 2:
            phases.reverse()
        for phase, prompt in phases:
            row = {"id": sample["id"], "phase": phase, "status": "inference_error",
                   "char_edits": None, "reference_chars": len(reference), "cer": None,
                   "duration_s": sample["duration_s"], "audio_sha256": sample["audio_sha256"]}
            started = perf_counter()
            try:
                text = stt_service.transcribe_audio_file_local(
                    str(sample["wav"]), sample["language"], initial_prompt=prompt,
                )
                if not text.strip():
                    row["status"] = "empty"
                else:
                    edits = edit_distance(reference, normalize(text))
                    row.update(status="ok", char_edits=edits, cer=edits / len(reference))
            except Exception:
                # No provider messages, paths, or reference/transcription text in reports.
                pass
            row["latency_ms"] = round((perf_counter() - started) * 1000, 3)
            rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    ids = {row["id"] for row in rows}
    paired = {sample_id for sample_id in ids if {
        row["phase"] for row in rows if row["id"] == sample_id and row["status"] == "ok"
    } == {"before", "after"}}
    summary = {"paired": len(paired), "failed": sum(row["status"] != "ok" for row in rows)}
    for phase in ("before", "after"):
        selected = [row for row in rows if row["id"] in paired and row["phase"] == phase]
        summary[phase] = {
            "cer": sum(row["char_edits"] for row in selected) / sum(row["reference_chars"] for row in selected) if selected else None,
            "mean_latency_ms": statistics.mean(row["latency_ms"] for row in selected) if selected else None,
        }
    return summary


def report_paths(directory: Path, tag: str) -> tuple[Path, Path]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tag):
        raise ValueError("Invalid output tag")
    prefix = datetime.now().strftime("%Y%m%d") + "_" + tag
    paths = directory / f"{prefix}.csv", directory / f"{prefix}.md"
    if any(path.exists() for path in paths):
        raise ValueError("Report exists; choose a different tag")
    return paths


def write_reports(rows, samples, directory: Path, tag: str, model_name: str):
    csv_path, md_path = report_paths(directory, tag)
    directory.mkdir(parents=True, exist_ok=True)
    summary = summarize(rows)
    fingerprint = hashlib.sha256(json.dumps([
        {"id": sample["id"], "reference": sample["reference"], "language": sample["language"],
         "audio_sha256": sample["audio_sha256"]} for sample in samples
    ], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with csv_path.open("x", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    model_label = model_name if re.fullmatch(r"[A-Za-z0-9_.-]+", model_name) else "custom model (path omitted)"
    lines = ["# STT initial_prompt 전후 측정", "",
             f"- 샘플 수: {len(samples)} / 양쪽 성공 쌍: {summary['paired']} / 실패 실행: {summary['failed']}",
             f"- 모델: {model_label} / CPU int8 / faster-whisper {version('faster-whisper')}",
             f"- 평가셋 SHA256: {fingerprint}",
             f"- 적용 prompt SHA256: {hashlib.sha256(stt_service.INITIAL_PROMPT.encode()).hexdigest()}",
             "- before: initial_prompt=None / after: 현재 기술 용어 initial_prompt", "",
             "| 조건 | 간이 CER (낮을수록 좋음) | 평균 인식 지연 ms |",
             "|---|---:|---:|"]
    for phase in ("before", "after"):
        metrics = summary[phase]
        cer = f"{metrics['cer']:.4f}" if metrics["cer"] is not None else "미측정"
        latency = f"{metrics['mean_latency_ms']:.3f}" if metrics["mean_latency_ms"] is not None else "미측정"
        lines.append(f"| {phase} | {cer} | {latency} |")
    lines.extend(["", "동일 WAV를 사용하고 모델 로딩·워밍업·ffmpeg 변환은 인식 지연에서 제외합니다. "
                  "샘플마다 before/after 순서를 번갈아 실행합니다. 지연은 STT 추론 구간이며 HTTP 지연이 아닙니다.", "",
                  "간이 CER은 NFKC·casefold 후 문자/숫자만 남겨 편집 거리 합 / 정답 문자 수 합으로 계산합니다. "
                  "CER은 1보다 클 수 있으며 정확도나 기술 용어 의미 판정으로 해석하지 않습니다. "
                  "이는 내부 측정 방식으로, 요구서가 지정한 공식 지표나 합격 기준이 아닙니다.", "",
                  "양쪽 성공 쌍만 비교표에 사용합니다. 실패 실행은 CSV에 남기며, "
                  "10쌍 미만이면 비교가 불완전하여 개선 여부를 확정할 수 없습니다. "
                  "실제 용어의 인식 적합성은 사람이 별도로 확인해야 합니다. "
                  "녹음 원본·정답·인식 원문·로컬 경로는 결과에 저장하지 않습니다. "
                  "합격 판정과 운영 모델의 자동 변경은 수행하지 않습니다.", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path, md_path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Local JSONL: id/audio/reference/language")
    parser.add_argument("--output-dir", type=Path, default=SERVICE_DIR / "data" / "stt-benchmark" / "results")
    parser.add_argument("--tag", default="prompt")
    parser.add_argument("--validate-only", action="store_true", help="Validate/decode all audio without loading Whisper")
    args = parser.parse_args(argv)
    try:
        samples = load_samples(args.manifest)
        if not args.validate_only:
            report_paths(args.output_dir, args.tag)
        # Input copies/WAVs are removed on validation, inference, or report failures.
        stt_service.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=stt_service.TEMP_DIR) as temporary:
            prepared = prepare_samples(samples, Path(temporary))
            if args.validate_only:
                print("Validated ten distinct audio files (10MB/60s); reference correctness requires human review.")
                return 0
            stt_service.initialize_model()
            rows = measure(prepared)
            paths = write_reports(rows, samples, args.output_dir, args.tag, stt_service.MODEL_NAME or "unknown")
        for path in paths:
            print(path)
        return 1 if any(row["status"] != "ok" for row in rows) else 0
    except Exception:
        print("STT benchmark cannot run: check ten distinct recordings, references, file formats/limits, "
              "ffmpeg, local model availability, and a unique output tag/path.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
