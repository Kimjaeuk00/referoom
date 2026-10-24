import os
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from faster_whisper import WhisperModel
from app.utils.audio_utils import AudioInputError, convert_to_wav, prepare_audio

# 1) Do not use GPU/MPS: fixed to CPU
DEVICE = "cpu"

# 2) Load model
#    Adjust to "base", "small", "medium", etc. as needed
#    On CPU, int8 provides better speed/memory stability.
model: WhisperModel | None = None
MODEL_NAME: str | None = None
_model_status = "not_ready"
TEMP_DIR = Path(__file__).resolve().parents[2] / "data" / "tmp"
INITIAL_PROMPT = (
    "LoRA, QLoRA, adapter, prefix-tuning, prompt tuning, PEFT, "
    "fine-tuning, low-rank, quantization, 하이퍼파라미터"
)


class ModelNotReadyError(RuntimeError):
    pass


class EmptyTranscriptionError(ValueError):
    pass


def initialize_model() -> None:
    """Load and warm up Whisper once during application startup."""
    global model, MODEL_NAME, _model_status
    if model is not None:
        return

    MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
    _model_status = "loading"
    try:
        loaded_model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type="int8")
        segments, _ = loaded_model.transcribe(
            np.zeros(16000, dtype=np.float32), language="ko", beam_size=1,
        )
        # Transcription is lazy: consume segments to actually run warm-up.
        for _ in segments:
            pass
    except Exception:
        _model_status = "failed"
        raise

    model = loaded_model
    _model_status = "ready"


def model_status() -> str:
    return _model_status


def convert_webm_to_wav(webm_path: str, wav_path: str) -> None:
    """
    Converts a webm file to a wav file.
    Calls ffmpeg directly. (More stable for installation/runtime than pydub)
    Sets mono channel + 16kHz for STT stability.
    """
    if not os.path.exists(webm_path):
        raise FileNotFoundError(f"Input not found: {webm_path}")

    out_dir = os.path.dirname(wav_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    convert_to_wav(Path(webm_path), Path(wav_path))


def _transcribe(
    file_path: str, language: str, *, initial_prompt: str | None = INITIAL_PROMPT,
) -> tuple[str, str]:
    """
    Performs STT using the local Whisper model.
    (Uses faster-whisper)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input not found: {file_path}")

    if model is None:
        raise ModelNotReadyError("Whisper model is not ready.")

    # faster-whisper returns a segments generator.
    segments, info = model.transcribe(
        file_path,
        beam_size=5,
        vad_filter=True,     # Remove silence (generally improves quality/speed)
        language=None if language == "auto" else language,
        initial_prompt=initial_prompt,
    )

    text = "".join(seg.text for seg in segments).strip()
    return text, info.language


def transcribe_audio_file_local(
    file_path: str, language: str = "ko", *, initial_prompt: str | None = INITIAL_PROMPT,
) -> str:
    text, _ = _transcribe(file_path, language, initial_prompt=initial_prompt)
    return text


def transcribe_upload(upload, filename: str | None, language: str) -> dict:
    if language not in {"ko", "en", "auto"}:
        raise AudioInputError("language는 ko, en, auto 중 하나여야 합니다.")
    if model is None:
        raise ModelNotReadyError("Whisper model is not ready.")
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    # TemporaryDirectory removes source and WAV in its finally/exit path,
    # including conversion, inference, and empty-transcription failures.
    with TemporaryDirectory(dir=TEMP_DIR) as temporary:
        wav_path, duration = prepare_audio(upload, filename, Path(temporary))
        text, detected_language = _transcribe(str(wav_path), language)
        if not text:
            raise EmptyTranscriptionError("음성을 인식하지 못했어요. 다시 말씀해 주세요.")
        return {"text": text, "language": detected_language, "duration_s": duration}


def transcribe_audio_file(file_path: str) -> str:
    """
    Wrapper for backward compatibility with existing code.
    (Ensures compatibility with code that previously used transcribe_audio_file)
    """
    return transcribe_audio_file_local(file_path)
