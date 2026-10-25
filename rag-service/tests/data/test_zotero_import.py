"""외부 라이브러리를 변경하지 않는 Zotero 등록 테스트."""

import asyncio
import io
import json
import unittest
from urllib.parse import parse_qs

import httpx
from pypdf import PdfWriter

from app.data.providers.arxiv import PaperCandidate
from app.data.providers.zotero import ZoteroProvider, ZoteroError


class ImportTest(unittest.TestCase):
    def test_import_and_retry(self):
        asyncio.run(self.run_import())

    async def run_import(self):
        writer = PdfWriter()
        writer.add_blank_page(72, 72)
        buffer = io.BytesIO()
        writer.write(buffer)
        pdf = buffer.getvalue()
        items, collections, uploads = {}, [], []
        pending = {}
        fail_storage = [True]

        class Arxiv:
            async def download_pdf_bytes(self, candidate):
                return pdf + candidate.version.encode()

        def handle(request):
            path = request.url.path
            if request.url.host == "storage.example.org":
                self.assertNotIn("Zotero-API-Key", request.headers)
                if fail_storage[0]:
                    return httpx.Response(503)
                uploads.append(request.content)
                return httpx.Response(201)
            self.assertEqual(request.headers["Zotero-API-Key"], "test-key")
            if request.method == "GET":
                if path.endswith("/collections"):
                    data = collections
                elif path.endswith("/items/top"):
                    data = [i for i in items.values() if "parentItem" not in i["data"]]
                elif path.endswith("/children"):
                    data = [i for i in items.values() if i["data"].get("parentItem") == path.split("/")[-2]]
                else:
                    data = items[path.split("/")[-1]]
                return httpx.Response(200, headers={"Last-Modified-Version": "1"}, json=data)
            if path.endswith("/file"):
                data = parse_qs(request.content.decode())
                key = path.split("/")[-2]
                if "upload" in data:
                    items[key]["data"].update(md5=pending["md5"], filename=pending["filename"])
                    return httpx.Response(204)
                pending.update({k: v[0] for k, v in data.items()})
                return httpx.Response(200, json={"url": "https://storage.example.org/upload",
                    "prefix": "prefix", "suffix": "suffix", "contentType": "multipart/form-data",
                    "uploadKey": "upload"})
            data = json.loads(request.content)
            if request.method == "PATCH":
                items[path.split("/")[-1]]["data"].update(data)
                return httpx.Response(204)
            data = data[0]
            key = f"KEY{len(items) + len(collections):05d}"
            item = {"key": key, "version": 1, "data": data}
            if path.endswith("/collections"):
                collections.append(item)
            else:
                items[key] = item
            return httpx.Response(200, json={"success": {"0": key}, "failed": {}})

        candidate = PaperCandidate(candidate_id="1902.00751", version="v2", title="Title",
            authors=["Author"], year=2019, abstract="Abstract",
            url="https://arxiv.org/abs/1902.00751v2", pdf_url="https://arxiv.org/pdf/1902.00751v2")
        async with ZoteroProvider(1, "test-key", transport=httpx.MockTransport(handle)) as provider:
            with self.assertRaises(ZoteroError):
                await provider.save_arxiv_paper(candidate, Arxiv())
            self.assertEqual(len(items), 2)
            self.assertNotIn("Referoom-Version", items["KEY00001"]["data"]["extra"])
            fail_storage[0] = False
            result = await provider.save_arxiv_paper(candidate, Arxiv())
            await provider.save_arxiv_paper(candidate, Arxiv())
            self.assertEqual((len(items), len(collections), len(uploads)), (2, 1, 1))
            self.assertEqual(items[result["paper_key"]]["data"]["abstractNote"], "Abstract")
            candidate.version = "v3"
            await provider.save_arxiv_paper(candidate, Arxiv())
            self.assertEqual((len(items), len(uploads)), (2, 2))
            candidate.version = "v1"
            self.assertEqual((await provider.save_arxiv_paper(candidate, Arxiv()))["status"], "kept")
            with self.assertRaises(ValueError):
                await provider.save_arxiv_paper(candidate, Arxiv(), pinned_version="v2")
