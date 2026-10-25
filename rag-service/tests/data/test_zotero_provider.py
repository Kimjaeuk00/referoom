"""Zotero provider 보완 기능 테스트. 가짜 Zotero 서버(MockTransport)만 쓰며 실제 그룹에는 쓰지 않는다."""
import asyncio
import hashlib
import json

import pytest

from app.data.providers.arxiv import PaperCandidate
from app.data.providers.zotero import ZoteroError, arxiv_id_of
from zotero_fake import FakeArxiv, FakeZotero, make_pdf


def candidate(version="v2"):
    return PaperCandidate(candidate_id="1902.00751", version=version, title="Parameter-Efficient Transfer Learning for NLP",
                          authors=["Neil Houlsby"], year=2019, abstract="Abstract",
                          url=f"https://arxiv.org/abs/1902.00751{version}", pdf_url=f"https://arxiv.org/pdf/1902.00751{version}")


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("data, expected", [
    ({"extra": "arXiv: 2306.05212\nReferoom-Version: v1"}, "2306.05212"),
    ({"extra": "arXiv:1902.00751 [cs.LG]"}, "1902.00751"),
    ({"extra": "ARXIV: 1902.00751v2"}, "1902.00751"),
    ({"extra": "arXiv:hep-th/9901001"}, "hep-th/9901001"),
    ({"url": "https://arxiv.org/abs/2106.09685v2"}, "2106.09685"),
    ({"url": "http://www.arxiv.org/pdf/2106.09685.pdf"}, "2106.09685"),
    ({"DOI": "10.48550/arXiv.2305.14314"}, "2305.14314"),
    ({"extra": "Referoom-Version: v1"}, None),
    ({"extra": "PMID: 12345678"}, None),
    ({"url": "https://example.org/abs/2106.09685"}, None),
    ({}, None),
])
def test_arxiv_id_of(data, expected):
    assert arxiv_id_of(data) == expected


def test_manual_item_with_pdf_is_reused_without_upload_or_overwrite():
    fake = FakeZotero()
    fake.adapter()
    before = json.dumps(fake.items, sort_keys=True)
    arxiv = FakeArxiv(make_pdf())

    async def go():
        async with fake.provider() as provider:
            return await provider.save_arxiv_paper(candidate(), arxiv)

    result = run(go())
    assert result["status"] == "kept" and result["pdf"] is None
    assert result["paper_key"] == "V3HSB2SA" and result["attachment_key"] == "8XQJP5SB"
    assert arxiv.calls == 0 and json.dumps(fake.items, sort_keys=True) == before  # 아무것도 쓰지 않았다


def test_pinned_version_on_manual_item_uploads_pdf_but_keeps_user_metadata():
    fake = FakeZotero()
    fake.adapter()
    pdf = make_pdf()

    async def go():
        async with fake.provider() as provider:
            return await provider.save_arxiv_paper(candidate("v2"), FakeArxiv(pdf), pinned_version="v2")

    result = run(go())
    paper = fake.items["V3HSB2SA"]["data"]
    assert result["status"] == "saved" and result["pdf"] == pdf and len(fake.uploads) == 1
    assert len([k for k, i in fake.items.items() if i["data"].get("itemType") != "attachment"]) == 1  # 논문 항목은 새로 안 생김
    assert paper["title"] == "내가 고친 제목" and paper["creators"][0]["lastName"] == "Houlsby"  # 덮어쓰지 않음
    assert paper["extra"].splitlines() == ["arXiv:1902.00751 [cs.LG]", "Referoom-Version: v2"]  # 표기 중복 없음
    assert fake.collections and fake.collections[0]["key"] in paper["collections"]


def test_new_item_returns_pdf_bytes_and_records_version():
    fake = FakeZotero()
    pdf = make_pdf(2)

    async def go():
        async with fake.provider() as provider:
            return await provider.save_arxiv_paper(candidate(), FakeArxiv(pdf))

    result = run(go())
    paper = fake.items[result["paper_key"]]["data"]
    assert result["status"] == "saved" and result["pdf"] == pdf
    assert paper["title"].startswith("Parameter-Efficient") and "Referoom-Version: v2" in paper["extra"]
    assert paper["extra"].splitlines().count("arXiv: 1902.00751") == 1


def test_arxiv_pdf_over_page_limit_is_rejected_before_any_write():
    fake = FakeZotero()

    async def go():
        async with fake.provider() as provider:
            await provider.save_arxiv_paper(candidate(), FakeArxiv(make_pdf(81)))

    with pytest.raises(ValueError, match="80"):
        run(go())
    assert fake.items == {} and fake.collections == []


def test_save_pdf_creates_item_with_attachment():
    fake = FakeZotero()
    pdf = make_pdf()

    async def go():
        async with fake.provider() as provider:
            return await provider.save_pdf(pdf, "my-paper.pdf", tags=["peft", " peft ", "", "lora"])

    result = run(go())
    paper = fake.items[result["paper_key"]]["data"]
    attachment = fake.items[result["attachment_key"]]["data"]
    assert paper["itemType"] == "preprint" and paper["title"] == "my-paper" and paper["extra"] == "Referoom-Upload"
    assert paper["tags"] == [{"tag": "peft"}, {"tag": "lora"}]
    assert attachment["parentItem"] == result["paper_key"] and attachment["filename"] == "my-paper.pdf"
    assert len(fake.uploads) == 1 and result["md5"] == hashlib.md5(pdf).hexdigest()


def test_save_pdf_trashes_parent_when_upload_fails():
    fake = FakeZotero()
    fake.storage_fail = True

    async def go():
        async with fake.provider() as provider:
            await provider.save_pdf(make_pdf(), "x.pdf")

    with pytest.raises(ZoteroError):
        run(go())
    parents = [i for i in fake.items.values() if "parentItem" not in i["data"]]
    assert len(parents) == 1 and parents[0]["data"]["deleted"] == 1


@pytest.mark.parametrize("pdf, name, message", [
    (b"hello", "a.pdf", "PDF"), (make_pdf(), "a.txt", "파일명"), (make_pdf(81), "a.pdf", "80"), (b"%PDF-1.4 broken", "a.pdf", "읽을 수 없습니다"),
])
def test_save_pdf_validation(pdf, name, message):
    fake = FakeZotero()

    async def go():
        async with fake.provider() as provider:
            await provider.save_pdf(pdf, name)

    with pytest.raises(ValueError, match=message):
        run(go())
    assert fake.items == {}


def test_trash_item_and_list_library():
    fake = FakeZotero()
    fake.adapter()
    fake.add("263A8NW8", itemType="preprint", title="RETA-LLM", extra="arXiv: 2306.05212")
    fake.add("4RDQ4ID6", itemType="attachment", parentItem="263A8NW8", linkMode="imported_file", contentType="application/pdf", md5="m")
    fake.add("JRNLART1", itemType="journalArticle", title="No PDF yet")
    fake.add("NOTE0001", itemType="note", note="memo")
    fake.add("ORPHAN01", itemType="attachment", parentItem="GONE0001", linkMode="imported_file", contentType="application/pdf")
    fake.add("ANNOT001", itemType="annotation", parentItem="8XQJP5SB")

    async def go():
        async with fake.provider() as provider:
            first = await provider.list_library()
            await provider.trash_item("263A8NW8")
            await provider.trash_item("263A8NW8")  # 두 번째는 아무 일도 하지 않는다
            return first, await provider.list_library()

    (papers, attachments, version), (after_papers, after_attachments, _) = run(go())
    assert version == 7
    assert {p["key"] for p in papers} == {"V3HSB2SA", "263A8NW8", "JRNLART1"}
    assert [a["key"] for a in attachments["V3HSB2SA"]] == ["8XQJP5SB"]  # linked_url·주석·고아 첨부는 제외
    assert set(attachments) == {"V3HSB2SA", "263A8NW8"}
    assert fake.items["263A8NW8"]["data"]["deleted"] == 1
    assert {p["key"] for p in after_papers} == {"V3HSB2SA", "JRNLART1"} and "263A8NW8" not in after_attachments
