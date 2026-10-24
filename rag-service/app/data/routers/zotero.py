"""Zotero 연결 상태와 동기화. 연결 설정(그룹 ID·키)은 서버 환경변수로만 관리한다."""
from fastapi import APIRouter, Depends

from app.data import ingest, repo
from app.data.deps import require_admin
from app.data.schemas import SyncResponse, ZoteroConfig
from app.rag import config_rag
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError

router = APIRouter(tags=["Zotero"])


@router.get("/zotero/config", response_model=ZoteroConfig, summary="Zotero 연결 상태")
async def get_config(user: CurrentUser = Depends(require_admin)) -> dict:
    configured = repo.is_configured(user.team_id)
    return {"configured": configured, "group_id": config_rag.ZOTERO_GROUP_ID if configured else None,
            "last_synced_at": repo.read_sync_state(user.team_id).get("last_synced_at") if configured else None}


@router.post("/zotero/sync", status_code=202, response_model=SyncResponse, summary="Zotero와 색인 맞추기")
async def sync(user: CurrentUser = Depends(require_admin)) -> dict:
    if not repo.is_configured(user.team_id):
        raise ApiError(409, "ZOTERO_NOT_CONFIGURED", "이 팀은 Zotero 그룹이 연결되지 않았습니다.")
    return {"batch_id": await ingest.start_sync(user.team_id)}


@router.post("/zotero/config", summary="Zotero 설정 저장 (지원하지 않음)")
@router.delete("/zotero/config", summary="Zotero 설정 삭제 (지원하지 않음)")
async def unsupported_config(user: CurrentUser = Depends(require_admin)) -> None:
    raise ApiError(405, "NOT_SUPPORTED", "Zotero 설정은 서버 .env로 관리합니다.")
