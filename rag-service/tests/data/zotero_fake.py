"""가짜 Zotero 서버·색인 저장소·arXiv와 PDF 생성기 (tests/data 공용). 실제 그룹·색인·네트워크는 쓰지 않는다."""
import io
import json
import threading
import time
from urllib.parse import parse_qs

import httpx
from pypdf import PdfWriter

from app.data.providers.zotero import ZoteroProvider
from app.rag.local_store.ingest import IngestError


def make_pdf(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(72, 72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FakeArxiv:
    def __init__(self, pdf: bytes):
        self.pdf, self.calls = pdf, 0

    async def download_pdf_bytes(self, candidate):
        self.calls += 1
        return self.pdf


class FakeZotero:
    """필요한 엔드포인트만 흉내 낸다: 목록·조회·생성·수정·파일 업로드."""

    def __init__(self):
        self.items, self.collections, self.uploads = {}, [], []
        self.pending, self.storage_fail, self.seq = {}, False, 0
        self.files = {}  # 첨부 key -> PDF 바이트 (다운로드용)
        self.list_calls = 0  # GET /items (전체 목록) 호출 수. 캐시 시험용

    def add(self, key, version=1, **data):
        self.items[key] = {"key": key, "version": version, "data": data}
        return self.items[key]

    def provider(self):
        return ZoteroProvider(1, "test-key", transport=httpx.MockTransport(self.handle))

    def _live(self):
        return [i for i in self.items.values() if not i["data"].get("deleted")]

    def handle(self, request):
        path = request.url.path
        if request.url.host == "storage.example.org":
            if self.storage_fail:
                return httpx.Response(503)
            self.uploads.append(request.content)
            self.last_upload = request.content  # 'p' + PDF + 's' (업로드 승인 응답의 prefix·suffix)
            return httpx.Response(201)
        assert request.headers["Zotero-API-Key"] == "test-key"
        headers = {"Last-Modified-Version": "7"}
        if request.method == "GET":
            if path.endswith("/collections"):
                data = self.collections
            elif path.endswith("/items/top"):
                data = [i for i in self._live() if "parentItem" not in i["data"]]
            elif path.endswith("/items"):
                self.list_calls += 1
                data = self._live()
            elif path.endswith("/children"):
                parent = path.split("/")[-2]
                data = [i for i in self._live() if i["data"].get("parentItem") == parent]
            elif path.endswith("/file"):
                content = self.files.get(path.split("/")[-2])
                return httpx.Response(404) if content is None else httpx.Response(200, headers=headers, content=content)
            else:
                data = self.items.get(path.split("/")[-1])
                if data is None:
                    return httpx.Response(404)
            return httpx.Response(200, headers=headers, json=data)
        if path.endswith("/file"):
            form = parse_qs(request.content.decode())
            key = path.split("/")[-2]
            if "upload" in form:
                self.items[key]["data"].update(md5=self.pending["md5"], filename=self.pending["filename"])
                self.files[key] = self.last_upload[1:-1]  # 올린 파일은 내려받을 수 있다
                return httpx.Response(204)
            self.pending = {k: v[0] for k, v in form.items()}
            return httpx.Response(200, json={"url": "https://storage.example.org/upload", "prefix": "p", "suffix": "s",
                                             "contentType": "multipart/form-data", "uploadKey": "upload"})
        body = json.loads(request.content)
        if request.method == "PATCH":
            self.items[path.split("/")[-1]]["data"].update(body)
            return httpx.Response(204)
        self.seq += 1
        key = f"NEW{self.seq:05d}"
        item = {"key": key, "version": 1, "data": body[0]}
        if path.endswith("/collections"):
            self.collections.append(item)
        else:
            self.items[key] = item
        return httpx.Response(200, json={"success": {"0": key}, "failed": {}})

    def adapter(self):
        """Zotero 앱에서 직접 추가한 논문: arXiv 표기가 'arXiv:ID [분류]', PDF 첨부는 사람이 붙인 파일명."""
        self.add("V3HSB2SA", itemType="preprint", title="내가 고친 제목", extra="arXiv:1902.00751 [cs.LG]",
                 creators=[{"creatorType": "author", "firstName": "Neil", "lastName": "Houlsby"}])
        self.add("8XQJP5SB", itemType="attachment", parentItem="V3HSB2SA", linkMode="imported_file",
                 contentType="application/pdf", filename="Houlsby - 2019 - Adapter.pdf", md5="abc123")
        self.add("M3J3RCDD", itemType="attachment", parentItem="V3HSB2SA", linkMode="linked_url",
                 contentType="", title="1902.00751")


SCAN = make_pdf(2)  # 가짜 저장소가 '스캔 PDF'로 취급하는 바이트


class FakeStore:
    """local_store.store의 일부를 흉내 낸다: 논문별 청크 수와 메타데이터를 메모리에 둔다."""

    def __init__(self):
        self.counts, self.metas, self.calls, self.deleted = {}, {}, [], []
        self.reject_scans = True
        self.running = self.max_running = 0
        self._lock = threading.Lock()

    def add_paper(self, team_id, paper_id, pdf, meta, replace=False):
        with self._lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            time.sleep(0.02)  # 팀 안에서 배치가 겹치지 않는지 볼 수 있게 잠깐 걸린다
            self.calls.append((team_id, paper_id, replace))
            if self.reject_scans and pdf == SCAN:
                raise IngestError("텍스트 추출 불가(스캔 PDF)")
            self.counts[paper_id], self.metas[paper_id] = 3, dict(meta)
            return {"chunk_count": 3, "references": None, "page_count": 1, "index_version": len(self.calls)}
        finally:
            with self._lock:
                self.running -= 1

    def delete_paper(self, team_id, paper_id):
        self.deleted.append(paper_id)
        self.metas.pop(paper_id, None)
        return self.counts.pop(paper_id, 0)

    def drop_team(self, team_id):
        self.counts.clear()
        self.metas.clear()

    def reload(self, team_id=None):
        pass

    def paper_chunk_counts(self, team_id):
        return dict(self.counts)

    def paper_ids_with_meta(self, team_id, field):
        return {pid for pid, meta in self.metas.items() if meta.get(field)}


class FakeArxivProvider:
    """arXiv 검색(search)과 PDF 다운로드(download_pdf_bytes)를 흉내 낸다."""

    def __init__(self, pdf=None, error=None, candidates=None):
        self.pdf, self.error, self.downloads = pdf or make_pdf(), error, []
        self.candidates, self.search_error, self.searches = candidates or [], None, []

    async def search(self, topic, max_results=10):
        self.searches.append(topic)
        if self.search_error:
            raise self.search_error
        return self.candidates[:max_results]

    async def download_pdf_bytes(self, candidate, **kwargs):
        if self.error:
            raise self.error
        self.downloads.append(candidate.candidate_id)
        return self.pdf
