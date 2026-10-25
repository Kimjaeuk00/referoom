"""RAG 서비스 설정 (환경변수 로딩). 이 파일에만 설정값을 둔다."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
# Zotero 값은 프로젝트 루트 .env에 있다. 이미 설정된 값은 덮어쓰지 않으므로 rag-service/.env가 우선한다
load_dotenv(Path(__file__).resolve().parents[3] / ".env")


def _optional_int(name: str) -> int | None:
    """비어 있거나 숫자가 아니면 None (설정 누락은 해당 기능이 409로 알린다)."""
    value = (os.getenv(name) or "").strip()
    return int(value) if value.isdecimal() and int(value) > 0 else None


# JWT_SECRET·발급자·CORS 허용 주소는 common-py(referoom_common.get_settings)가 환경변수에서 읽는다. 여기에 두지 않는다.

# 근거 판정 임계값 (DEV_04 3.2절). 임베딩 모델마다 점수 분포가 다르므로 모델을 바꾸면 다시 보정한다.
# bge-m3/1000자, 질문 30개: 정상 1위 점수 0.570~0.756, 예외 0.446~0.601 (DoRA만 0.601로 겹침 → LLM found=false가 처리)
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.55"))
REVIEW_SCORE = float(os.getenv("REVIEW_SCORE", "0.60"))  # 정상 질문 중 하위 3/24가 검수 대상

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

# ---- Zotero 그룹 (논문 라이브러리의 원천, app/data) ----
# 그룹은 ZOTERO_TEAM_ID 한 팀에만 연결한다. 키는 로그·응답·예외 메시지에 넣지 않는다
ZOTERO_GROUP_ID = _optional_int("ZOTERO_GROUP_ID")
ZOTERO_API_KEY = (os.getenv("ZOTERO_API_KEY") or "").strip() or None
ZOTERO_TEAM_ID = _optional_int("ZOTERO_TEAM_ID") or int(os.getenv("LOCAL_TEAM_ID", "3"))
ZOTERO_CACHE_SECONDS = int(os.getenv("ZOTERO_CACHE_SECONDS", "30"))  # 논문 목록 캐시. 쓰기 뒤에는 바로 비운다
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local")  # local(sentence-transformers) | openai
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")  # 30문항 비교 1위: MRR 0.740 (3-small 0.664, 3-large 0.539)

# ---- 선행연구 후보 검색 (app/data, /search-topic) ----
# 후보의 관련도 = 주제 질의와 '제목+초록'의 bge-m3 코사인. 아래 값 미만은 low_relevance 경고만 붙이고 막지는 않는다
TOPIC_MIN_RELEVANCE = float(os.getenv("TOPIC_MIN_RELEVANCE", "0.50"))  # 0.45→0.50: arXiv 후보 40건(질의 4개) 점수 0.43~0.74, 무관한 결과 0.43·0.47, 관련 결과 ≥0.53. 표본이 작아 후보가 쌓이면 다시 본다
TOPIC_CACHE_SECONDS = int(os.getenv("TOPIC_CACHE_SECONDS", "600"))  # 검색한 후보를 /upload-topic이 다시 쓰도록 보관하는 시간

# ---- v0.2 모드 (선행연구 정리표·주제 제안·원고 검증·논문 요약) ----
# 아래 값은 호출 수·지연·비용의 상한을 정하는 시작값이다. 실제 논문으로 측정하기 전이라 '미측정'으로 표시하고, 측정하면 근거를 적어 바꾼다.
# 선행연구: 논문마다 LLM 추출 1회 + 비교 답변 1회. 논문 수가 많을수록 호출이 늘어 병렬도와 근거량에 상한을 둔다
PRIOR_MAX_PAPERS = int(os.getenv("PRIOR_MAX_PAPERS", "10"))  # 한 번에 비교할 논문 수. 프론트의 한 번에 수집·선택 상한(10)과 같다
PRIOR_CHUNKS_PER_PAPER = int(os.getenv("PRIOR_CHUNKS_PER_PAPER", "4"))  # 논문당 근거 청크. 1000자 청크 4개 ≈ 4,000자 (미측정)
PRIOR_WORKERS = int(os.getenv("PRIOR_WORKERS", "4"))  # 논문별 추출을 동시에 부르는 스레드 수. OpenAI 속도 제한에 걸리면 줄인다 (미측정)
PRIOR_CELL_MAX_CHARS = int(os.getenv("PRIOR_CELL_MAX_CHARS", "300"))  # 표 한 칸의 글자 수 상한. 프롬프트는 100자 안팎을 요청하고 넘치는 값만 자른다 (미측정)
# 주제 제안
TOPIC_MAX_PAPERS = int(os.getenv("TOPIC_MAX_PAPERS", "10"))  # 대상 논문 상한 (요청 검증과 같은 값)
TOPIC_CHUNKS_PER_PAPER = int(os.getenv("TOPIC_CHUNKS_PER_PAPER", "3"))  # '한계·향후 연구' 질의로 논문당 모으는 청크 (미측정)
TOPIC_LIMITS_PER_PAPER = int(os.getenv("TOPIC_LIMITS_PER_PAPER", "2"))  # 논문 한 편에서 뽑는 한계 수. 후보 4개가 서로 다른 한계를 쓰기에 충분한 양으로 잡은 값 (미측정)
TOPIC_SIMILAR_SEARCH_K = int(os.getenv("TOPIC_SIMILAR_SEARCH_K", "20"))  # 유사 연구를 찾으려고 검색하는 청크 수. 선택한 논문의 청크를 빼고도 남도록 넉넉히 (미측정)
TOPIC_WORKERS = int(os.getenv("TOPIC_WORKERS", "4"))  # 논문별 한계 추출을 동시에 부르는 스레드 수 (미측정)
TOPIC_TEXT_MAX_CHARS = int(os.getenv("TOPIC_TEXT_MAX_CHARS", "300"))  # 한계 요약·후보 문장 하나의 글자 수 상한 (미측정)
TOPIC_LIST_MAX_ITEMS = int(os.getenv("TOPIC_LIST_MAX_ITEMS", "5"))  # 후보의 데이터셋·비교 대상·지표 목록마다의 항목 수 상한
TOPIC_SIMILAR_MAX = int(os.getenv("TOPIC_SIMILAR_MAX", "3"))  # 후보마다 보여 주는 유사 연구 수
TOPIC_SIMILAR_MIN_SCORE = float(os.getenv("TOPIC_SIMILAR_MIN_SCORE", "0.60"))  # 이 값 이상일 때만 '라이브러리 안의 유사 연구'로 보인다. REVIEW_SCORE와 같은 값에서 시작, 후보 질문-논문 점수 분포는 미측정
# 원고 검증
VERIFY_MAX_CLAIMS = int(os.getenv("VERIFY_MAX_CLAIMS", "12"))  # 한 원고에서 대조할 주장 수. 넘으면 앞에서부터 처리하고 warnings로 알린다 (원고 3,000자 기준 미측정)
VERIFY_EVIDENCE_CHUNKS = int(os.getenv("VERIFY_EVIDENCE_CHUNKS", "3"))  # 주장마다 모으는 근거 청크 (미측정)
VERIFY_WORKERS = int(os.getenv("VERIFY_WORKERS", "4"))  # 주장별 근거 읽기를 동시에 부르는 스레드 수 (미측정)
VERIFY_TEXT_MAX_CHARS = int(os.getenv("VERIFY_TEXT_MAX_CHARS", "300"))  # 주장 문장·값·조건 하나의 글자 수 상한 (미측정)
# 논문 요약
SUMMARY_CHUNKS_PER_SECTION = int(os.getenv("SUMMARY_CHUNKS_PER_SECTION", "3"))  # 섹션 하나를 쓰려고 모으는 청크 (미측정)
