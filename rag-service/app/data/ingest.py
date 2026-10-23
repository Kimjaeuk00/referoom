import os
import tempfile

from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .chunker import chunk_paper
from .pdf_parser import load_paper
from .store import save_pdf_store


async def ingest_pdf(file: UploadFile):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 허용됩니다.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        try:
            paper_text = load_paper(tmp_path)
        finally:
            os.unlink(tmp_path)

        if not paper_text.strip():
            raise HTTPException(
                status_code=422,
                detail="PDF에서 텍스트를 추출하지 못했습니다. 스캔 PDF라면 OCR이 필요합니다.",
            )

        docs = chunk_paper(paper_text, file.filename)
        save_pdf_store(docs)

        return JSONResponse(content={
            "message": f"{len(docs)}개의 PDF 청크 벡터화 및 저장 완료",
            "extracted_characters": len(paper_text),
            "preview": paper_text[:300],
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
