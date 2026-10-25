"""수집·업로드·동기화 배치의 진행 상황. 프론트가 주기적으로 조회한다."""
from fastapi import APIRouter, Depends

from app.data import ingest
from app.data.deps import require_library
from app.data.schemas import BatchOut
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError

router = APIRouter(tags=["배치"])


@router.get("/ingest/batches/{batch_id}", response_model=BatchOut, summary="배치 진행 상황")
async def get_batch(batch_id: int, user: CurrentUser = Depends(require_library)) -> dict:
    batch = ingest.get_batch(user.team_id, batch_id)  # 다른 팀의 배치는 없는 것과 같다
    if batch is None:
        raise ApiError(404, "NOT_FOUND", "배치를 찾을 수 없습니다.")
    return batch
