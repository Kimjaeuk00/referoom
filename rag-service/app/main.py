from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.data.routers import batches, library, upload, zotero
from app.rag import config_rag
from app.rag.errors import register_error_handlers
from app.rag.router import router as rag_router

if not config_rag.JWT_SECRET:
    raise RuntimeError("JWT_SECRET 환경변수가 설정되지 않았습니다.")

app = FastAPI(title="Referoom RAG Service", description="팀 논문 근거 기반 질의응답 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config_rag.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_error_handlers(app)
app.include_router(rag_router)
for data_router in (library.router, upload.router, batches.router, zotero.router):
    app.include_router(data_router)
