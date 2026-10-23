"""Zotero 그룹 조회 및 arXiv 논문 등록. PDF는 메모리로 전달합니다."""

import asyncio
import hashlib
import uuid
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import BaseModel


class ZoteroError(RuntimeError):
    """응답 본문이나 API 키를 포함하지 않는 외부 API 오류."""


class ZoteroChanges(BaseModel):
    # 첨부·주석만 바뀐 경우도 ingest가 부모 논문에 반영할 수 있도록 보존합니다.
    items: list[dict[str, Any]]
    deleted_keys: list[str]
    library_version: int


class ZoteroPaper(BaseModel):
    zotero_key: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    url: str | None
    tags: list[str]


def parse_paper(item: dict[str, Any]) -> ZoteroPaper | None:
    data = item["data"]
    if data.get("itemType") not in {"journalArticle", "preprint", "conferencePaper"}:
        return None
    year = re.search(r"\b(?:19|20)\d{2}\b", data.get("date", ""))
    return ZoteroPaper(
        zotero_key=item["key"], title=data.get("title", ""),
        authors=[creator.get("name") or " ".join(filter(None, (
            creator.get("firstName"), creator.get("lastName"))))
            for creator in data.get("creators", []) if creator.get("creatorType") == "author"],
        year=int(year.group()) if year else None,
        doi=data.get("DOI") or None, url=data.get("url") or None,
        tags=[tag["tag"] for tag in data.get("tags", [])],
    )


class ZoteroProvider:
    """async with로 사용합니다. 키 로딩·암호화 저장과 DB/색인은 호출 측 책임입니다."""

    def __init__(self, group_id: int, api_key: str, *, timeout: float = 30.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        if group_id <= 0 or not api_key.strip():
            raise ValueError("그룹 ID와 API 키가 필요합니다.")
        self._root = f"https://api.zotero.org/groups/{group_id}"
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self._lock = asyncio.Lock()
        self._import_lock = asyncio.Lock()
        self._not_before = 0.0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    @staticmethod
    def _key(key: str) -> str:
        if re.fullmatch(r"[A-Z0-9]{8}", key) is None:
            raise ValueError("Zotero 항목 키는 영문 대문자·숫자 8자리여야 합니다.")
        return key

    @staticmethod
    def _delay(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                return 0.0

    async def _request(self, path: str, *, params: dict | None = None,
                       pdf_limit: int | None = None) -> tuple[bytes, httpx.Headers]:
        async with self._lock:
            for attempt in range(3):
                url = httpx.URL(self._root + path)
                query = params
                try:
                    for redirect in range(6):
                        await asyncio.sleep(max(0.0, self._not_before - time.monotonic()))
                        headers = {"User-Agent": "Referoom/0.1"}
                        # 다운로드 저장소로 리다이렉트될 때 Zotero 키를 전달하지 않습니다.
                        if url.host == "api.zotero.org":
                            headers.update({"Zotero-API-Key": self._api_key, "Zotero-API-Version": "3"})
                        async with self._client.stream("GET", url, params=query, headers=headers) as response:
                            delay = max(self._delay(response.headers.get("Backoff")),
                                        self._delay(response.headers.get("Retry-After")))
                            self._not_before = time.monotonic() + delay
                            status = response.status_code
                            if status == 429 or 500 <= status < 600:
                                if attempt == 2:
                                    raise ZoteroError(f"Zotero 요청 재시도 실패 (HTTP {status})")
                                self._not_before = max(self._not_before, time.monotonic() + 2 ** attempt)
                                break
                            if status in {301, 302, 303, 307, 308}:
                                location = response.headers.get("Location")
                                if not location or redirect == 5:
                                    raise ZoteroError("PDF 다운로드 리다이렉트 오류")
                                url = response.url.join(location)
                                if url.scheme != "https" or url.userinfo:
                                    raise ZoteroError("안전하지 않은 다운로드 주소입니다.")
                                query = None
                                continue
                            if status in {401, 403}:
                                raise ZoteroError("ZOTERO_AUTH_FAILED: 그룹 읽기·파일 접근 권한을 확인하세요.")
                            if status == 404:
                                raise ZoteroError("Zotero 항목 또는 업로드된 첨부 파일이 없습니다.")
                            if status != 200:
                                raise ZoteroError(f"Zotero 요청 실패 (HTTP {status})")
                            content = bytearray()
                            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                                if pdf_limit is not None and len(content) + len(chunk) > pdf_limit:
                                    raise ZoteroError("PDF 최대 크기를 초과했습니다.")
                                content.extend(chunk)
                            if pdf_limit is not None and not content.startswith(b"%PDF-"):
                                raise ZoteroError("첨부 데이터가 PDF 형식이 아닙니다.")
                            return bytes(content), response.headers
                except httpx.TransportError:
                    if attempt == 2:
                        raise ZoteroError("Zotero 네트워크 요청에 실패했습니다.") from None
                    self._not_before = max(self._not_before, time.monotonic() + 2 ** attempt)
            raise ZoteroError("Zotero 요청을 완료하지 못했습니다.")

    async def _json(self, path: str, **params) -> tuple[Any, int]:
        import json
        content, headers = await self._request(path, params=params)
        try:
            return json.loads(content), int(headers["Last-Modified-Version"])
        except (ValueError, KeyError):
            raise ZoteroError("Zotero JSON 또는 버전 헤더가 올바르지 않습니다.") from None

    async def _items(self, path: str, *, since: int = 0) -> tuple[list[dict], int]:
        if since < 0:
            raise ValueError("동기화 버전은 0 이상이어야 합니다.")
        items = []
        version = None
        while True:
            page, current = await self._json(path, since=since, format="json", limit=100, start=len(items))
            if not isinstance(page, list):
                raise ZoteroError("Zotero 항목 목록 형식이 올바르지 않습니다.")
            if version is not None and current != version:
                raise ZoteroError("조회 중 라이브러리가 변경됐습니다. 기존 버전으로 다시 동기화하세요.")
            version = current
            items.extend(page)
            if len(page) < 100:
                return items, version

    async def check_connection(self) -> int:
        """그룹 읽기 권한 확인. 파일 권한은 실제 PDF 다운로드로 확인합니다."""
        _, version = await self._json("/items", format="json", limit=1)
        return version

    async def get_item(self, key: str) -> dict:
        item, _ = await self._json(f"/items/{self._key(key)}", format="json")
        return item

    async def get_changes(self, since: int = 0) -> ZoteroChanges:
        """전체/증분 항목과 삭제 키를 반환합니다. 성공 후 버전 저장은 ingest가 수행합니다.

        첨부·주석의 parentItem도 처리해야 하며, 부분 실패 항목은 재시도 대상으로
        별도 보관한 뒤 버전을 갱신해야 실패한 항목을 놓치지 않습니다.
        """
        items, version = await self._items("/items", since=since)
        deleted, deleted_version = await self._json("/deleted", since=since)
        if version != deleted_version:
            raise ZoteroError("조회 중 라이브러리가 변경됐습니다. 기존 버전으로 다시 동기화하세요.")
        return ZoteroChanges(items=items, deleted_keys=deleted["items"], library_version=version)

    async def get_pdf_attachments(self, paper_key: str) -> list[dict]:
        children, _ = await self._items(f"/items/{self._key(paper_key)}/children")
        return [item for item in children if item["data"].get("itemType") == "attachment"
                and item["data"].get("contentType") == "application/pdf"
                and item["data"].get("linkMode") in {"imported_file", "imported_url"}]

    async def get_annotations(self, attachment_key: str) -> list[dict]:
        """P1: annotationText/Comment/PageLabel 등 원본 필드를 반환합니다."""
        children, _ = await self._items(f"/items/{self._key(attachment_key)}/children")
        return [item for item in children if item["data"].get("itemType") == "annotation"]

    async def download_pdf(self, attachment_key: str, *, max_pdf_mb: int = 20) -> bytes:
        """디스크 저장 없이 반환합니다. 해시 계산·80페이지 제한 검사는 ingest에서 수행합니다."""
        if max_pdf_mb <= 0:
            raise ValueError("PDF 크기 제한은 양수여야 합니다.")
        content, _ = await self._request(f"/items/{self._key(attachment_key)}/file",
                                       pdf_limit=max_pdf_mb * 1024 * 1024)
        return content

    async def _write(self, method: str, path: str, *, expected=(200, 204), **kwargs) -> httpx.Response:
        """쓰기 결과가 불명확한 네트워크 오류는 자동 재시도하지 않습니다."""
        headers = {"Zotero-API-Key": self._api_key, "Zotero-API-Version": "3",
                   **kwargs.pop("headers", {})}
        async with self._lock:
            for attempt in range(3):
                await asyncio.sleep(max(0.0, self._not_before - time.monotonic()))
                try:
                    response = await self._client.request(method, self._root + path, headers=headers, **kwargs)
                except httpx.TransportError:
                    raise ZoteroError("쓰기 결과를 확인하지 못했습니다. 다시 조회한 뒤 재시도하세요.") from None
                delay = max(self._delay(response.headers.get("Backoff")),
                            self._delay(response.headers.get("Retry-After")))
                self._not_before = time.monotonic() + delay
                if response.status_code == 429 and attempt < 2:
                    self._not_before = max(self._not_before, time.monotonic() + 2 ** attempt)
                    continue
                if response.status_code not in expected:
                    raise ZoteroError(f"Zotero 저장 실패 (HTTP {response.status_code}). 쓰기·파일 권한과 저장 용량을 확인하세요.")
                return response
        raise ZoteroError("Zotero 저장 요청 제한을 초과했습니다.")

    async def _create(self, path: str, data: dict) -> str:
        response = await self._write("POST", path, json=[data],
                                     headers={"Zotero-Write-Token": uuid.uuid4().hex})
        body = response.json()
        if body.get("failed"):
            raise ZoteroError("Zotero 항목 생성에 실패했습니다. 항목 유형과 필드를 확인하세요.")
        key = body.get("success", {}).get("0")
        if key is None:
            key = body.get("successful", {}).get("0", {}).get("key")
        if not key:
            raise ZoteroError("Zotero 생성 결과에 항목 키가 없습니다.")
        return self._key(key)

    async def ensure_collection(self, name: str = "arXiv 수집") -> str:
        """같은 이름의 최상위 컬렉션을 재사용합니다."""
        if not name.strip():
            raise ValueError("컬렉션 이름이 필요합니다.")
        collections, _ = await self._items("/collections")
        for item in collections:
            if item["data"].get("name") == name and not item["data"].get("parentCollection"):
                return item["key"]
        return await self._create("/collections", {"name": name, "parentCollection": False})

    async def upload_pdf(self, attachment_key: str, pdf: bytes, filename: str,
                         *, previous_md5: str | None = None) -> None:
        """첨부 생성 후 업로드 승인 → 저장소 전송 → 등록. 원본 파일은 만들지 않습니다."""
        if not pdf.startswith(b"%PDF-") or len(pdf) > 20 * 1024 * 1024:
            raise ValueError("20MB 이하의 PDF 데이터가 필요합니다.")
        path = f"/items/{self._key(attachment_key)}/file"
        condition = {"If-Match": previous_md5} if previous_md5 else {"If-None-Match": "*"}
        response = await self._write("POST", path, headers=condition, data={
            "md5": hashlib.md5(pdf).hexdigest(), "filename": filename,
            "filesize": str(len(pdf)), "mtime": str(int(time.time() * 1000)),
        })
        auth = response.json()
        if auth.get("exists"):
            return
        url = httpx.URL(auth["url"])
        if url.scheme != "https" or url.userinfo:
            raise ZoteroError("안전하지 않은 업로드 주소입니다.")
        # 이 요청에는 Zotero API 키를 전달하지 않습니다. 자동 리다이렉트도 금지합니다.
        try:
            response = await self._client.post(url, content=(auth["prefix"].encode() + pdf + auth["suffix"].encode()),
                                               headers={"Content-Type": auth["contentType"]})
        except httpx.TransportError:
            raise ZoteroError("PDF 저장소 업로드에 실패했습니다. 다시 조회 후 재시도하세요.") from None
        if response.status_code != 201:
            raise ZoteroError(f"PDF 저장소 업로드 실패 (HTTP {response.status_code})")
        await self._write("POST", path, headers=condition, data={"upload": auth["uploadKey"]}, expected=(204,))

    async def save_arxiv_paper(self, candidate, arxiv_provider, *,
                               collection_name: str = "arXiv 수집",
                               pinned_version: str | None = None) -> dict:
        """사용자가 선택한 후보 1편을 등록합니다. 후보 검색이나 색인은 실행하지 않습니다.

        실패 시 이미 생성된 논문/첨부는 남기고 재시도에 재사용합니다. 서로 다른
        프로세스의 동시 등록은 호출 측의 팀별 락으로 직렬화해야 합니다.
        """
        from .arxiv import _version_number
        incoming = _version_number(candidate.version)
        if pinned_version is not None:
            _version_number(pinned_version)
        if pinned_version is not None and candidate.version != pinned_version:
            raise ValueError("시드·평가 논문은 지정된 고정 버전으로 등록해야 합니다.")
        marker = f"arXiv: {candidate.candidate_id}"
        async with self._import_lock:
            items, _ = await self._items("/items/top")
            matches = [item for item in items if marker in item["data"].get("extra", "").splitlines()
                       or re.fullmatch(r"https?://arxiv\.org/abs/" + re.escape(candidate.candidate_id) + r"(?:v\d+)?/?",
                                       item["data"].get("url", ""))]
            if len(matches) > 1:
                raise ZoteroError("같은 arXiv 논문이 여러 개 있습니다. Zotero에서 중복을 정리하세요.")
            paper = matches[0] if matches else None
            if paper:
                version = re.search(r"^Referoom-Version: (v\d+)$", paper["data"].get("extra", ""), re.M)
                if version and pinned_version is not None and version[1] != pinned_version:
                    raise ValueError("Zotero에 저장된 버전이 평가 고정 버전과 다릅니다.")
                if version and _version_number(version[1]) > incoming:
                    return {"paper_key": paper["key"], "status": "kept"}
            # 원격 쓰기 전에 다운로드와 문서 제한을 검증합니다.
            pdf = await arxiv_provider.download_pdf_bytes(candidate)
            import pymupdf
            with pymupdf.open(stream=pdf, filetype="pdf") as document:
                if document.page_count > 80:
                    raise ValueError("PDF는 최대 80페이지까지 등록할 수 있습니다.")
            collection = await self.ensure_collection(collection_name)
            metadata = {"itemType": "preprint", "title": candidate.title,
                        "abstractNote": candidate.abstract, "date": str(candidate.year),
                        "url": candidate.url,
                        "creators": [{"creatorType": "author", "name": name} for name in candidate.authors]}
            if paper is None:
                key = await self._create("/items", {**metadata, "collections": [collection], "extra": marker})
                paper = await self.get_item(key)
            key = paper["key"]
            filename = candidate.candidate_id.replace("/", "_") + candidate.version + ".pdf"
            attachments = await self.get_pdf_attachments(key)
            # 업로드된 파일은 생략하고, 중단된 첨부 항목도 재사용합니다.
            attachment = next((item for item in attachments if item["data"].get("filename") == filename), None)
            if attachment is None and paper:
                managed = [item for item in attachments if re.fullmatch(
                    re.escape(candidate.candidate_id.replace("/", "_")) + r"v\d+\.pdf",
                    item["data"].get("filename", ""))]
                if len(managed) == 1:
                    attachment = managed[0]
            digest = hashlib.md5(pdf).hexdigest()
            if attachment is None:
                attachment_key = await self._create("/items", {
                    "itemType": "attachment", "parentItem": key, "linkMode": "imported_file",
                    "title": filename, "filename": filename, "contentType": "application/pdf"})
                previous_md5 = None
            else:
                attachment_key = attachment["key"]
                previous_md5 = attachment["data"].get("md5")
            if previous_md5 != digest:
                await self.upload_pdf(attachment_key, pdf, filename, previous_md5=previous_md5)
            if attachment is not None and attachment["data"].get("title") != filename:
                current_attachment = await self.get_item(attachment_key)
                await self._write("PATCH", f"/items/{attachment_key}", expected=(204,),
                    headers={"If-Unmodified-Since-Version": str(current_attachment["version"])},
                    json={"title": filename})
            # PDF登録成功後にだけ完了バージョンを記録します。既存タグ等は保持します。
            paper = await self.get_item(key)
            data = paper["data"]
            extra = [line for line in data.get("extra", "").splitlines()
                     if not line.startswith("Referoom-Version:") and line != marker]
            extra.extend([marker, f"Referoom-Version: {candidate.version}"])
            if candidate.doi and not any(line.startswith("DOI:") for line in extra):
                extra.append(f"DOI: {candidate.doi}")
            await self._write("PATCH", f"/items/{key}", expected=(204,),
                headers={"If-Unmodified-Since-Version": str(paper["version"])},
                json={**metadata, "extra": "\n".join(extra),
                      "collections": list(dict.fromkeys([*data.get("collections", []), collection]))})
            return {"paper_key": key, "attachment_key": attachment_key,
                    "collection_key": collection, "status": "saved", "version": candidate.version}
