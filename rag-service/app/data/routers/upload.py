from fastapi import APIRouter, File, UploadFile

from ..ingest import ingest_pdf


router = APIRouter()


@router.post("/upload-paper", summary="PDF 업로드 및 벡터화", tags=["PDF 처리"])
async def upload_pdf(file: UploadFile = File(...)):
    return await ingest_pdf(file)
