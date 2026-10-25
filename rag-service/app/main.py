from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from referoom_common import RequestLoggingMiddleware, get_settings

from app.data.routers import batches, library, upload, zotero
from app.rag import config_rag  # noqa: F401  (.env를 읽는다. get_settings()보다 먼저 불러와야 한다)
from app.rag.errors import register_error_handlers
from app.rag.router import router as rag_router
from app.rag.router_modes import router as modes_router

# JWT_SECRET이 없으면 여기서 RuntimeError로 서버가 뜨지 않는다. 발급자·알고리즘·CORS 허용 주소는 common-py 설정을 따른다.
settings = get_settings()

app = FastAPI(title="Referoom RAG Service", description="팀 논문 근거 기반 질의응답 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)
register_error_handlers(app)
app.include_router(rag_router)
app.include_router(modes_router)
for data_router in (library.router, upload.router, batches.router, zotero.router):
    app.include_router(data_router)

# 마지막에 추가해 가장 바깥에서 모든 요청(CORS 사전 요청 포함)을 기록한다. in_tok/out_tok은 라우터가 request.state에 넣는다.
app.add_middleware(RequestLoggingMiddleware)
