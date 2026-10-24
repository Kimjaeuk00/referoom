"""RAG 서비스 설정 (환경변수 로딩). 이 파일에만 설정값을 둔다."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ISSUER = "simple-auth-server"

# 근거 판정 임계값 (DEV_04 3.2절). 임베딩 모델마다 점수 분포가 다르므로 모델을 바꾸면 다시 보정한다.
# bge-m3/1000자, 질문 30개: 정상 1위 점수 0.570~0.756, 예외 0.446~0.601 (DoRA만 0.601로 겹침 → LLM found=false가 처리)
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.55"))
REVIEW_SCORE = float(os.getenv("REVIEW_SCORE", "0.60"))  # 정상 질문 중 하위 3/24가 검수 대상

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5174,http://localhost:8008").split(",")
    if o.strip()
]

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))  # 추론 모델에는 보내지 않는다 (llm.py)
# 추론 모델의 추론 강도(none|low|medium|high). 비우면 API 기본값. 지연·출력 토큰에 직접 영향
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT") or None
# 이미지 재시도에만 쓰는 모델 (비우면 LLM_MODEL). 텍스트 답은 빠른 모델, 그래프·표 판독은 다른 모델로 나눌 때 쓴다
LLM_IMAGE_MODEL = os.getenv("LLM_IMAGE_MODEL") or LLM_MODEL
LLM_IMAGE_REASONING_EFFORT = os.getenv("LLM_IMAGE_REASONING_EFFORT") or LLM_REASONING_EFFORT

# 질문 시 페이지 이미지 투입 (실험): 표·그림·수식 표시가 붙은 근거 페이지를 이미지로 LLM에 함께 넣는다
PAGE_IMAGES = os.getenv("PAGE_IMAGES", "off") == "on"
PAGE_IMAGES_ON_REFUSAL = os.getenv("PAGE_IMAGES_ON_REFUSAL", "off") == "on"  # 실험: 텍스트가 거절해도 이미지로 재시도
# 검색 상위 k개 안의 캡션 청크 최대 개수 (비우면 제한 없음). 캡션이 본문 청크 자리를 차지하는 것을 막는다
MAX_CAPTION_HITS = int(os.getenv("MAX_CAPTION_HITS")) if os.getenv("MAX_CAPTION_HITS") else None
PAGE_IMAGE_MAX = int(os.getenv("PAGE_IMAGE_MAX", "2"))  # 질문당 최대 페이지 수 (비용·지연 상한)
PAGE_IMAGE_SCALE = float(os.getenv("PAGE_IMAGE_SCALE", "2.5"))  # 72dpi 기준 배율 (2.5 ≈ 180dpi). OpenAI가 리사이즈해 토큰은 1.5와 같고 그래프 판독은 나았다

# ---- 로컬 검색 저장소 (데이터 파트 store.py 도착 전 개발·비교용, app/rag/local_store) ----
# stub: 고정 더미 / local: 아래 로컬 색인 / (추후) data: 데이터 파트 store.py
STORE_BACKEND = os.getenv("RAG_STORE", "stub")
LOCAL_TEAM_ID = int(os.getenv("LOCAL_TEAM_ID", "3"))
SEED_DIR = Path(os.getenv("SEED_DIR", str(Path(__file__).resolve().parents[3] / "data" / "seed")))
LOCAL_INDEX_DIR = Path(os.getenv("LOCAL_INDEX_DIR", str(Path(__file__).resolve().parent / ".cache" / "local_index")))
# 적재한 원본 PDF 보관 위치 ({PDF_DIR}/{team_id}/{paper_id}.pdf). 이미지 재시도가 원본 페이지를 렌더링할 때 쓴다
PDF_DIR = Path(os.getenv("PDF_DIR", str(Path(__file__).resolve().parent / ".cache" / "pdfs")))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))  # 500→1000: Hit@1 0.38→0.62, MRR 0.52→0.73 (dev_eval, 3-small)
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
# 1단계 레이아웃 정리 규칙: 머리말·꼬리말 제거, 표 숫자 붙이기, 캡션 청크, has_table, 엄격한 has_math
LAYOUT_RULES = os.getenv("LAYOUT_RULES", "on") == "on"
PDF_READER = os.getenv("PDF_READER", "pypdf")  # pypdf(BSD) | pymupdf(AGPL, 비교 실험용)
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local")  # local(sentence-transformers) | openai
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")  # 30문항 비교 1위: MRR 0.740 (3-small 0.664, 3-large 0.539)
