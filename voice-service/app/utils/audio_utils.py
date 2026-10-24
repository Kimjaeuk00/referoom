"""Validate uploaded audio and normalize it using ffmpeg."""

from pathlib import Path
import subprocess
import wave


MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 60
SUPPORTED_EXTENSIONS = {".webm", ".ogg", ".mp4", ".m4a", ".wav"}


class AudioInputError(ValueError):
    def __init__(self, message, status_code=422, code="VALIDATION_ERROR"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def convert_to_wav(source: Path, destination: Path, limit_seconds=None) -> None:
    command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
               "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-vn"]
    if limit_seconds is not None:
        command.extend(["-t", str(limit_seconds)])
    command.extend(["-c:a", "pcm_s16le", str(destination)])
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise AudioInputError("오디오 파일을 읽을 수 없습니다. 다른 파일로 다시 시도해 주세요.")


def prepare_audio(upload, filename: str | None, directory: Path) -> tuple[Path, float]:
    extension = Path(filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise AudioInputError("지원하는 오디오 형식은 webm, ogg, mp4, m4a, wav입니다.")

    # Only the validated suffix is used; discard the client-supplied filename.
    source = directory / f"input{extension}"
    total = 0
    with source.open("wb") as output:
        while chunk := upload.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_AUDIO_BYTES:
                raise AudioInputError("오디오는 10MB 이하여야 합니다.", 413, "PAYLOAD_TOO_LARGE")
            output.write(chunk)
    if total == 0:
        raise AudioInputError("비어 있는 오디오 파일입니다.")

    destination = directory / "normalized.wav"
    # Decode at most 61 seconds: enough to reject over-limit input without
    # writing an arbitrarily long decoded recording to disk.
    convert_to_wav(source, destination, MAX_AUDIO_SECONDS + 1)
    with wave.open(str(destination), "rb") as normalized:
        duration = normalized.getnframes() / normalized.getframerate()
    if duration <= 0:
        raise AudioInputError("비어 있는 오디오 파일입니다.")
    if duration > MAX_AUDIO_SECONDS:
        raise AudioInputError("오디오는 60초 이하여야 합니다.")
    return destination, duration
