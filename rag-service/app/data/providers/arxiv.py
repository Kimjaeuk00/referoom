"""arXiv 후보 검색·버전 판단·선택한 PDF 다운로드. 색인은 ingest에서 수행합니다."""

import asyncio
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel


class PaperCandidate(BaseModel):
    candidate_id: str
    version: str | None = None
    title: str
    authors: list[str]
    year: int
    abstract: str
    url: str
    pdf_url: str
    doi: str | None = None


class SearchProvider(Protocol):
    async def search(self, topic: str, max_results: int = 10) -> list[PaperCandidate]: ...


class VersionDecision(BaseModel):
    action: Literal["add", "replace", "keep"]
    candidate: PaperCandidate


def _version_number(version: str | None) -> int:
    if version is None or re.fullmatch(r"v[1-9]\d*", version) is None:
        raise ValueError("논문 버전은 v1, v2 같은 형식으로 확인해야 합니다.")
    return int(version[1:])


def select_version(
    incoming: PaperCandidate,
    current: PaperCandidate | None = None,
    *,
    pinned_version: str | None = None,
) -> VersionDecision:
    """같은 팀의 기존 논문과 비교합니다. 실제 DB·인덱스 변경은 수행하지 않습니다.

    일반 논문은 더 최신 버전만 교체 대상으로 반환합니다.
    시드·평가 논문은 manifest.csv의 version을 pinned_version으로 전달해야 합니다.
    호출 측은 replace일 때 기존 paper_id를 유지하며 해당 논문만 재색인합니다.
    """
    if current is not None and current.candidate_id != incoming.candidate_id:
        raise ValueError("서로 다른 논문은 버전 교체 대상으로 비교할 수 없습니다.")

    if pinned_version is not None:
        _version_number(pinned_version)
        if current is not None:
            if current.version != pinned_version:
                raise ValueError("저장된 평가 논문의 버전이 고정 버전과 다릅니다. 확인이 필요합니다.")
            return VersionDecision(action="keep", candidate=current)
        if incoming.version != pinned_version:
            raise ValueError(f"평가용 논문은 {pinned_version} PDF를 가져와야 합니다.")
        return VersionDecision(action="add", candidate=incoming)

    incoming_number = _version_number(incoming.version)
    if current is None:
        return VersionDecision(action="add", candidate=incoming)
    if incoming_number > _version_number(current.version):
        return VersionDecision(action="replace", candidate=incoming)
    return VersionDecision(action="keep", candidate=current)


_request_lock = asyncio.Lock()
_last_request = 0.0
_namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def parse_candidates(xml: str) -> list[PaperCandidate]:
    root = ET.fromstring(xml)
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise ValueError("arXiv 응답이 Atom feed 형식이 아닙니다.")
    candidates = []
    for entry in root.findall("atom:entry", _namespace):
        def value(name: str) -> str:
            return " ".join((entry.findtext(name, default="", namespaces=_namespace)).split())

        entry_url = value("atom:id")
        if "/api/errors" in entry_url:
            raise ValueError(f"arXiv 검색 오류: {value('atom:summary')}")
        if "/abs/" not in entry_url:
            raise ValueError("arXiv 논문 ID가 없는 응답입니다.")
        versioned_id = entry_url.split("/abs/", 1)[1]
        match = re.fullmatch(r"(.+?)(v\d+)?", versioned_id)
        paper_id, version = match.groups()
        candidates.append(PaperCandidate(
            candidate_id=paper_id,
            version=version,
            title=value("atom:title"),
            authors=[" ".join((author.findtext("atom:name", default="", namespaces=_namespace)).split())
                     for author in entry.findall("atom:author", _namespace)],
            year=int(value("atom:published")[:4]),
            abstract=value("atom:summary"),
            url=f"https://arxiv.org/abs/{versioned_id}",
            pdf_url=f"https://arxiv.org/pdf/{versioned_id}",
            doi=value("arxiv:doi") or None,
        ))
    return candidates


class ArxivProvider:
    """단일 프로세스·이벤트 루프에서 요청 간격을 공유합니다."""

    def __init__(self, user_agent: str = "Referoom/0.1", timeout: float = 30.0):
        self.user_agent = user_agent
        self.timeout = timeout

    async def download_pdf(
        self,
        candidate: PaperCandidate,
        destination: str | Path,
        *,
        max_pdf_mb: int = 20,
    ) -> Path:
        """선택한 버전의 PDF를 지정 경로에 저장합니다. 기존 파일은 덮어쓰지 않습니다.

        ingest가 임시 경로를 전달하고 사용 후 정리합니다. 시드·평가용 버전은
        호출 전에 select_version()으로 확인해야 합니다. 페이지 수 제한은 파서
        연결 단계에서 검사합니다. 후보에 들어 있는 임의 URL 대신 ID로 주소를 만듭니다.
        """
        global _last_request
        _version_number(candidate.version)
        if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[A-Za-z][A-Za-z0-9.-]*/\d{7})", candidate.candidate_id) is None:
            raise ValueError("유효한 arXiv 논문 ID가 필요합니다.")
        if max_pdf_mb <= 0:
            raise ValueError("PDF 크기 제한은 양수여야 합니다.")
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError(f"저장 경로에 파일이 이미 있습니다: {destination}")
        url = f"https://arxiv.org/pdf/{candidate.candidate_id}{candidate.version}"
        limit = max_pdf_mb * 1024 * 1024
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True,
            headers={"User-Agent": self.user_agent},
        ) as client:
            async with _request_lock:
                for attempt in range(3):
                    await asyncio.sleep(max(0.0, 3.0 - (time.monotonic() - _last_request)))
                    _last_request = time.monotonic()
                    try:
                        async with client.stream("GET", url) as response:
                            if response.status_code == 429 or 500 <= response.status_code < 600:
                                if attempt < 2:
                                    await asyncio.sleep(3 * 2**attempt)
                                    continue
                            response.raise_for_status()
                            content = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                                if len(content) + len(chunk) > limit:
                                    raise ValueError(f"PDF가 최대 크기 {max_pdf_mb}MB를 초과했습니다.")
                                content.extend(chunk)
                                if len(content) >= 5 and not content.startswith(b"%PDF-"):
                                    raise ValueError("다운로드한 파일이 PDF 형식이 아닙니다.")
                            if not content.startswith(b"%PDF-"):
                                raise ValueError("다운로드한 파일이 비어 있거나 PDF 형식이 아닙니다.")
                    except httpx.TransportError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(3 * 2**attempt)
                        continue
                    return await asyncio.to_thread(_save_pdf, destination, content)
        raise RuntimeError("arXiv PDF 다운로드를 완료하지 못했습니다.")

    async def search(self, topic: str, max_results: int = 10) -> list[PaperCandidate]:
        global _last_request
        topic = " ".join(topic.split())
        if not topic or len(topic) > 300:
            raise ValueError("주제는 1~300자로 입력하세요.")
        if not 1 <= max_results <= 100:
            raise ValueError("후보 개수는 1~100으로 지정하세요.")
        # 사용자의 키워드를 검색식 전체가 아닌 하나의 구문으로 전달합니다.
        topic = topic.replace('"', " ")
        params = {"search_query": f'all:"{topic}"', "start": 0,
                  "max_results": max_results, "sortBy": "relevance"}
        async with httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": self.user_agent}) as client:
            # 재시도 대기 동안에도 다른 검색이 먼저 요청하지 않도록 잠금을 유지합니다.
            async with _request_lock:
                for attempt in range(3):
                    await asyncio.sleep(max(0.0, 3.0 - (time.monotonic() - _last_request)))
                    _last_request = time.monotonic()
                    try:
                        response = await client.get("https://export.arxiv.org/api/query", params=params)
                    except httpx.TransportError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(3 * 2**attempt)
                        continue
                    if response.status_code == 429 or 500 <= response.status_code < 600:
                        if attempt < 2:
                            await asyncio.sleep(3 * 2**attempt)
                            continue
                    response.raise_for_status()
                    return parse_candidates(response.text)
        raise RuntimeError("arXiv 후보 검색을 완료하지 못했습니다.")


def _save_pdf(destination: Path, content: bytes | bytearray) -> Path:
    """완료된 파일만 공개하고, 기존 경로는 덮어쓰지 않습니다."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            temporary.write(content)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        os.link(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination
