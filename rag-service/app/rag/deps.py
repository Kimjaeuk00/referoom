"""스텁 ↔ 로컬 ↔ 실제 구현 교체 지점. 검색 저장소와 인증은 이 파일에서만 고른다. 인증은 common-py를 쓴다.

RAG_STORE 환경변수: stub(기본, 테스트용 더미) | local(app/rag/local_store 색인)
데이터 파트 store.py가 오면 아래 분기에 한 줄을 추가한다.
"""
from referoom_common import CurrentUser, require_team

from app.rag import config_rag

if config_rag.STORE_BACKEND == "local":
    from app.rag.local_store import store
else:
    from app.rag import store_stub as store  # TODO(data): from app.data import store

__all__ = ["store", "require_team", "CurrentUser"]
