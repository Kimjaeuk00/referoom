"""질문이 이름을 든 라이브러리 논문을 찾고, 논문별로 따로 검색해 합친다 (튜터 경로).

비교 질문은 하나의 순위로 검색하면 한 논문(주로 LoRA·QLoRA)이 상위를 채워 다른 논문이 빠진다. 이름이 2편 이상 잡힌 질문만 처리하고,
그 밖의 질문은 기존 검색 결과를 그대로 쓴다. 별칭 표와 점수 하한의 근거는 config_rag.py에 있다.
"""
import re

from app.rag import config_rag

_ASCII = re.compile(r"[a-z0-9]")


def aliases_of(titles: dict[int, str]) -> dict[int, list[str]]:
    """논문 id → 질문에서 그 논문을 가리키는 표기(소문자). 제목 콜론 앞 이름과 config_rag.PAPER_ALIASES 표를 합친다."""
    out: dict[int, list[str]] = {}
    for pid, title in titles.items():
        names: set[str] = set()
        head = title.split(":", 1)[0].strip().lower()
        if ":" in title and 2 <= len(head) <= 30:
            names.add(head)
        for key, aliases in config_rag.PAPER_ALIASES.items():
            if key.lower() in title.lower():
                names.update(a.lower() for a in aliases)
        if names:
            out[pid] = sorted(names)
    return out


def detect(question: str, aliases: dict[int, list[str]]) -> list[int]:
    """질문에 이름이 나온 논문 id(나온 순서 무관, 중복 없음). 긴 표기부터 지워 가며 찾아 QLoRA 안의 LoRA를 따로 세지 않는다."""
    text = question.lower()
    pairs = sorted(((a, pid) for pid, names in aliases.items() for a in names), key=lambda x: -len(x[0]))
    found: list[int] = []
    for alias, pid in pairs:
        start = 0
        while True:
            i = text.find(alias, start)
            if i < 0:
                break
            before = text[i - 1] if i > 0 else " "
            after = text[i + len(alias)] if i + len(alias) < len(text) else " "
            # 영문 표기는 다른 영단어의 일부(colorado 안의 lora)로 잡히지 않게 경계를 본다. 한국어 표기는 조사가 붙으므로 경계를 보지 않는다.
            if _ASCII.match(alias[0]) and (_ASCII.match(before) or _ASCII.match(after)):
                start = i + 1
                continue
            if pid not in found:
                found.append(pid)
            text = text[:i] + " " * len(alias) + text[i + len(alias):]
            break
    return found


def merge(base: list, per_paper: list[list], k: int) -> list:
    """논문별 후보를 번갈아 하나씩 담고(논문마다 1위, 2위, …), 남는 자리는 기존 검색 결과로 채운다. 점수순으로 돌려준다."""
    out: list = []
    rank = 0
    while len(out) < k and any(rank < len(hits) for hits in per_paper):
        for hits in per_paper:
            if rank < len(hits) and len(out) < k:
                out.append(hits[rank])
        rank += 1
    for h in base:
        if len(out) >= k:
            break
        if all(h.text != o.text for o in out):
            out.append(h)
    return sorted(out, key=lambda h: -h.score)
