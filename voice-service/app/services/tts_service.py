import os
from pathlib import Path
import requests


class TtsNotReadyError(RuntimeError):
    pass


class TtsUpstreamError(RuntimeError):
    pass


def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    """Generate MP3 bytes without logging input, credentials, or provider errors."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("낭독할 텍스트를 입력해 주세요.")
    selected_voice = voice if voice is not None else os.getenv("TTS_VOICE", "nova")
    if not isinstance(selected_voice, str) or not selected_voice.strip():
        raise ValueError("음성을 지정해 주세요.")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("TTS_MODEL", "tts-1")
    if not api_key or not api_key.strip() or not model.strip():
        raise TtsNotReadyError("음성 합성 서비스를 준비 중입니다.")
    url = "https://api.openai.com/v1/audio/speech"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "input": text,
        "voice": selected_voice,
        "response_format": "mp3",
    }

    try:
        # User-confirmed connect/read inactivity limits; not a total deadline.
        response = requests.post(url, headers=headers, json=data, timeout=(5, 30))
        try:
            response.raise_for_status()
            content = response.content
        finally:
            response.close()
    except requests.RequestException:
        raise TtsUpstreamError("음성 합성 응답을 받지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    if not content:
        raise TtsUpstreamError("음성 합성 응답을 받지 못했습니다. 잠시 후 다시 시도해 주세요.")
    return content


def text_to_speech(text: str, output_path: str = "output.mp3"):
    """Compatibility helper for unregistered legacy demo code."""
    content = synthesize_speech(text)
    Path(output_path).write_bytes(content)
    return output_path
