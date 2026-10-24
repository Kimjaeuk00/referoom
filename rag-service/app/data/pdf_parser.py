import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

import pymupdf


PageTexts = list[tuple[int, str]]
SCAN_ERROR = "텍스트 추출 불가(스캔 PDF)"
REFERENCE_HEADING = re.compile(
    r"^\s*(?:(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+)?"
    r"(?:references|bibliography|참고\s*문헌)\s*[:：]?\s*$",
    re.IGNORECASE,
)


@dataclass
class ReferenceSection:
    start_page: int
    end_page: int
    text: str
    type: Literal["references"] = field(default="references", init=False)


@dataclass
class ParseResult:
    status: Literal["completed", "failed"]
    # 색인 대상 본문만 포함하며, 원래 PDF의 1부터 시작하는 페이지 번호를 유지합니다.
    pages: PageTexts = field(default_factory=list)
    references: ReferenceSection | None = None
    error_msg: str | None = None


def extract_pages(file_path: str | bytes) -> PageTexts:
    """파일 경로 또는 PDF bytes에서 추출합니다. 빈 페이지를 포함하며 OCR은 수행하지 않습니다."""
    # bytes 입력은 디스크에 저장하지 않고 메모리에서 직접 엽니다.
    document = (
        pymupdf.open(stream=file_path, filetype="pdf")
        if isinstance(file_path, bytes)
        else pymupdf.open(file_path)
    )
    with document:
        return [
            (page_no, page.get_text("text") or "")
            for page_no, page in enumerate(document, start=1)
        ]


def _normalize_line(line: str) -> str:
    return " ".join(line.split())


def _remove_page_noise(pages: PageTexts) -> PageTexts:
    page_lines = [
        (page_no, [line.strip() for line in text.splitlines()])
        for page_no, text in pages
    ]
    edge_counts: Counter[str] = Counter()
    for _, lines in page_lines:
        nonempty = [_normalize_line(line) for line in lines if line.strip()]
        if nonempty:
            # 같은 페이지의 첫 줄과 끝 줄이 같아도 한 번만 계산합니다.
            edge_counts.update({nonempty[0], nonempty[-1]})

    # 한 페이지에만 있는 문장을 반복 머리말로 판정하지 않습니다.
    threshold = max(2, math.ceil(len(pages) * 0.5))
    repeated = {line for line, count in edge_counts.items() if count >= threshold}
    cleaned = []
    for page_no, lines in page_lines:
        nonempty_indices = [i for i, line in enumerate(lines) if line]
        edges = {nonempty_indices[0], nonempty_indices[-1]} if nonempty_indices else set()
        kept = [
            line
            for i, line in enumerate(lines)
            if not re.fullmatch(r"\d+", line)
            and not (i in edges and _normalize_line(line) in repeated)
        ]
        cleaned.append((page_no, "\n".join(kept)))
    return cleaned


def _clean_text(text: str) -> str:
    # 영문 단어의 줄 끝 하이픈만 결합합니다. 페이지 경계는 넘지 않습니다.
    text = re.sub(r"(?<=[A-Za-z])[-\u00ad][ \t]*\n[ \t]*(?=[A-Za-z])", "", text)
    # 빈 줄로 구분된 문단은 유지하고, 문단 안의 줄바꿈은 공백으로 바꿉니다.
    paragraphs = re.split(r"\n\s*\n", text.strip())
    return "\n\n".join(
        normalized
        for paragraph in paragraphs
        if (normalized := " ".join(paragraph.split()))
    )


def _split_references(pages: PageTexts) -> tuple[PageTexts, ReferenceSection | None]:
    body = []
    reference_parts = []
    start_page = None
    end_page = None
    in_references = False
    for page_no, text in pages:
        body_lines = []
        reference_lines = []
        for line in text.splitlines(keepends=True):
            if (
                not in_references
                and REFERENCE_HEADING.fullmatch(line.strip())
            ):
                in_references = True
                start_page = page_no
            if in_references:
                reference_lines.append(line)
            else:
                body_lines.append(line)

        # 같은 페이지에 남아 있는 본문은 보존하고, 참고문헌 전용 페이지는 제외합니다.
        body_text = _clean_text("".join(body_lines))
        if body_text or not in_references:
            body.append((page_no, body_text))
        reference_text = _clean_text("".join(reference_lines))
        if reference_text:
            reference_parts.append(reference_text)
            end_page = page_no

    references = None
    if start_page is not None and end_page is not None:
        references = ReferenceSection(
            start_page=start_page,
            end_page=end_page,
            text="\n\n".join(reference_parts),
        )
    return body, references


def has_math(text: str, min_markers: int = 3) -> bool:
    """청크 단위로 호출할 수식 휴리스틱입니다. 수식 복원이나 정확한 판별은 보장하지 않습니다."""
    markers = re.findall(r"\$|\\frac\b|∑|=", text)
    return len(markers) >= min_markers


def load_paper(file_path: str | bytes) -> ParseResult:
    """파일 경로 또는 PDF bytes를 받아 본문과 참고문헌을 분리합니다.

    PyMuPDF를 실험용으로 사용하며, 다단 문장 순서와 수식 추출 품질은
    실제 2단 시드 논문 3편으로 비교한 뒤 정식 채택 여부를 결정합니다.
    """
    try:
        pages = extract_pages(file_path)
    except Exception as exc:
        return ParseResult(status="failed", error_msg=f"PDF 텍스트 추출 실패: {exc}")

    # 머리말 제거 전, 공백을 제외한 추출 문자 수로 판단합니다.
    total_chars = sum(len(re.sub(r"\s", "", text)) for _, text in pages)
    if not pages or total_chars / len(pages) < 50:
        return ParseResult(status="failed", error_msg=SCAN_ERROR)

    cleaned_pages = _remove_page_noise(pages)
    body, references = _split_references(cleaned_pages)
    return ParseResult(status="completed", pages=body, references=references)



