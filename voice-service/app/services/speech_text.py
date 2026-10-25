"""Deterministic narration derived from the answer; no extra LLM calls."""
import html
import re

LIMIT = 600
NOTICE = "자세한 내용은 화면을 확인하세요."
HANDOFF = "논문 라이브러리에서 관련 내용을 찾지 못했어요. 논문 추가를 요청해 보세요."


def make_speech_text(answer: str, handoff: bool = False) -> str:
    if handoff:
        return HANDOFF
    text = html.unescape(answer)
    text = re.sub(r"\$\$[\s\S]*?\$\$|\$[^$]*?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)", "(수식은 화면을 참고하세요)", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[S\d+\]", "", text, flags=re.I)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"```[^\n]*\n|```", "", text)
    text = re.sub(r"(?m)^\s*(?:#{1,6}\s*|>\s*|[-+*]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"[*_`~|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    budget = LIMIT - len(NOTICE) - 1
    if len(text) > budget:
        head = text[:budget]
        ends = list(re.finditer(r"[.!?。！？](?:\s|$)", head))
        text = head[:ends[-1].start()+1].strip() if ends else ""
    return (text + " " if text else "") + NOTICE
