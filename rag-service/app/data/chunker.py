from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .pdf_parser import PageTexts, has_math


def chunk_paper(
    pages: PageTexts,
    metadata: dict[str, Any],
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[Document]:
    """ParseResult.pages의 본문만 받아 페이지별로 청킹합니다.

    metadata에는 team_id, paper_id, source(논문 제목)를 전달해야 합니다.
    DB·수집 단계에서 확보한 나머지 메타데이터도 함께 전달합니다.
    references는 전달하지 않습니다. 반환한 Document.id는 저장소에서
    FAISS의 ids로 전달해야 삭제·롤백에 같은 ID를 사용할 수 있습니다.
    """
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_size는 양수이고 chunk_overlap은 0 이상 chunk_size 미만이어야 합니다.")

    for key in ("team_id", "paper_id", "source"):
        if key not in metadata or metadata[key] is None:
            raise ValueError(f"필수 청크 메타데이터가 없습니다: {key}")

    chunk_type = metadata.get("type", "body")
    if chunk_type not in {"body", "annotation", "web"}:
        raise ValueError("색인할 청크 type은 body, annotation, web 중 하나여야 합니다.")

    base_metadata = {
        "zotero_key": None,
        "doi": None,
        "arxiv_id": None,
        "year": None,
        "tags": "",
        "url": None,
        "license": "unknown",
        "batch_id": None,
        **metadata,
        "type": chunk_type,
    }
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    chunks = []
    for page_no, text in pages:
        if not text.strip():
            continue

        # 페이지마다 따로 분할하여 청크가 페이지 경계를 넘지 않도록 합니다.
        page_docs = splitter.create_documents(
            [text],
            metadatas=[{**base_metadata, "page": page_no}],
        )
        for doc in page_docs:
            doc.id = f"{metadata['paper_id']}:{chunk_type}:{len(chunks) + 1}"
            doc.metadata["has_math"] = has_math(doc.page_content)
            chunks.append(doc)

    return chunks
