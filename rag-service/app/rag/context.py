"""검색 결과(Hit) → [S#] 라벨 컨텍스트 (DEV_04 3.3절)."""
from dataclasses import dataclass, field

MAX_CONTEXT_CHARS = 12000


@dataclass
class Block:
    label: str
    paper_id: int | None
    title: str
    page: int | None
    url: str | None
    type: str  # body | annotation | web
    texts: list[str] = field(default_factory=list)
    has_math: bool = False
    visual: bool = False  # 표·그림·수식이 섞인 블록 (원본 페이지 이미지가 도움이 되는 경우)
    score: float = 0.0

    @property
    def text(self) -> str:
        return "\n".join(self.texts)


def build_blocks(hits: list, max_chars: int = MAX_CONTEXT_CHARS) -> list[Block]:
    """같은 논문·페이지·유형의 청크는 한 블록으로 합친다. 총 글자 수는 max_chars 이내."""
    by_key: dict[tuple, Block] = {}
    total = 0
    for h in hits:
        m = h.metadata
        key = (m.get("paper_id"), m.get("page"), m.get("type", "body"))
        remaining = max_chars - total
        if remaining <= 0:
            break
        text = h.text[:remaining]
        block = by_key.get(key)
        if block is None:
            block = Block(
                label=f"S{len(by_key) + 1}",
                paper_id=m.get("paper_id"),
                title=m.get("source", ""),
                page=m.get("page"),
                url=m.get("url"),
                type=m.get("type", "body"),
            )
            by_key[key] = block
        block.texts.append(text)
        block.has_math = block.has_math or bool(m.get("has_math"))
        block.visual = block.visual or bool(m.get("has_math") or m.get("has_table") or m.get("kind") == "caption")
        block.score = max(block.score, h.score)
        total += len(text)
    return list(by_key.values())


def render_context(blocks: list[Block]) -> str:
    parts = []
    for b in blocks:
        page = f" p.{b.page}" if b.page is not None else ""
        note = " (팀원 주석)" if b.type == "annotation" else ""
        parts.append(f"[{b.label}] 《{b.title}》{page}{note}\n{b.text}")
    return "\n\n".join(parts)
