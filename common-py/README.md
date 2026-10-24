# referoom-common 적용 가이드

RAG·음성 서비스에서 함께 사용하는 JWT 인증, 팀·관리자 권한, 오류 응답, 요청 로그 패키지다. 패키지 설치 이름은 `referoom-common`, Python import 이름은 `referoom_common`이다.

백엔드 담당자가 `common-py/`를 관리하고, 각 서비스 담당자가 자신의 환경·진입점·라우터에 적용한다. 이 문서의 서비스 코드는 적용 예시이며, 이 문서 작성만으로 각 서비스에 반영된 것은 아니다.

## 1. 설치

Python 3.11 이상이 필요하다. 아래 명령은 저장소 루트 `referoom/`에서 시작한다. 이미 서비스 가상환경이 있으면 환경 생성 명령은 생략하고 기존 환경을 활성화한다.

### RAG 서비스

```bash
cd rag-service
python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements-data.txt -r requirements-rag.txt
python -m pip install -e ../common-py
python -m pip check

python -c "from referoom_common import CurrentUser, require_team; print('common-py import OK')"
```

`requirements-rag.txt`와 RAG 앱 코드는 RAG 담당자의 구현 브랜치에 있다. 아직 해당 변경을 받지 않은 브랜치에서는 구현 변경을 먼저 반영한 뒤 설치한다. 빈 requirements 파일을 새로 만들어 대체하지 않는다.

### 음성 서비스

새 터미널에서 저장소 루트를 기준으로 실행한다.

```bash
cd voice-service
python3.11 -m venv .venv
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m pip install -e ../common-py
python -m pip check

python -c "from referoom_common import CurrentUser, require_team; print('common-py import OK')"
```

`-e`는 현재 소스에 연결하는 개발용 설치다. RAG 가상환경에 설치한 패키지가 음성 가상환경에도 설치되는 것은 아니므로 각 환경에서 실행한다. 공통 패키지는 FastAPI와 **PyJWT**를 의존성으로 설치한다. 기존 서비스의 `python-jose`와 다른 패키지이며, 다른 코드가 아직 사용한다면 임의로 제거하지 않는다.

공통 패키지는 Whisper·LLM SDK·FFmpeg·Uvicorn을 제공하지 않는다. 모델과 서버 실행에 필요한 의존성은 각 서비스가 관리한다. 각 서비스의 고정 버전과 함께 `pip check` 및 서비스 테스트를 실행한다.

### Docker 적용 시

서비스 Dockerfile 담당자와 배포 담당자가 **저장소 루트를 build context로 사용**하도록 맞춰야 형제 폴더인 `common-py/`를 복사할 수 있다. 예를 들어 해당 context를 전제로 서비스 Dockerfile에 다음 단계를 추가할 수 있다.

```dockerfile
COPY common-py/ /opt/referoom-common/
RUN python -m pip install --no-cache-dir /opt/referoom-common
```

컨테이너에는 일반 설치를 사용한다. context가 바뀌면 기존 서비스 코드·requirements의 `COPY` 경로도 함께 조정해야 한다. 기존 음성 Dockerfile은 서비스 폴더 기준으로 작성되어 있으므로 위 두 줄만 추가하면 배포가 끝나는 것은 아니다. Compose와 다른 서비스 파일 변경은 각 소유자가 진행한다.

## 2. 환경변수

각 서비스 프로세스에 아래 값을 전달한다.

- `JWT_SECRET`: 필수. Java 인증 서버와 **완전히 동일한 문자열**을 사용한다. 임의의 새 키를 Python에만 만들면 Java 토큰을 검증할 수 없다. 이 패키지는 키를 strip하거나 Base64로 다시 해석하지 않는다.
- `CORS_ALLOWED_ORIGINS`: 쉼표로 구분한 브라우저 origin. 기본값은 `http://localhost:5174,http://localhost:8008`이다. 빈 목록과 `*`는 허용하지 않는다. 실제 프론트 주소에 맞춘다.

현재 발급자 `simple-auth-server`와 알고리즘 `HS256`은 공통 설정에 고정되어 있다. `JWT_ISSUER`나 `JWT_ALGORITHM` 환경변수를 추가해도 이 패키지의 값은 바뀌지 않는다. 발급 서버 계약이 바뀌면 백엔드 담당자와 함께 변경한다.

서비스 `.env` 예시는 다음과 같다. 키 자리표시자는 실제 값으로 바꾸고 Git에는 올리지 않는다.

```dotenv
JWT_SECRET='JAVA와_동일한_실제_비밀키로_교체'
CORS_ALLOWED_ORIGINS=http://localhost:5174,http://localhost:8008
```

`common-py`는 `.env`를 자동으로 읽지 않는다. 셸에서 주입하거나 서비스가 설정을 조회하기 전에 `.env`를 로딩해야 한다. 셸 방식은 **현재 서비스 폴더에서** 다음처럼 실행한다.

```bash
set -a
source ./.env
set +a
```

음성 서비스는 기존 `app/main.py`에서 서비스 `.env`와 과거 `app/.env`를 읽고 있다. 이 로딩은 유지하되 사용하지 않는 과거 키가 남아 있지 않은지 확인한다. RAG 서비스도 환경변수 로딩을 자신의 설정 초기화보다 먼저 수행해야 한다.

`get_settings()`는 첫 조회 결과를 캐시한다. 실행 중 `.env` 파일만 수정해도 설정이 갱신되지는 않으므로 환경을 다시 주입하고 서버를 재시작한다. 실제 키를 로그·Swagger 예시·프론트 `VITE_*`에 넣지 않는다.

## 3. 서비스 시작점: 예외·로그·CORS 등록

아래는 독립적인 최소 예시다. 기존 서비스에는 새 `FastAPI()`를 하나 더 만들지 말고, **현재 `app` 생성 이후, 서버 시작 전에** 등록 부분을 적용한다. 기존 lifespan, 모델 초기화, 정적 파일, 헬스체크와 라우터는 유지한다.

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from referoom_common import (
    RequestLoggingMiddleware,
    get_settings,
    register_error_handlers,
)

# 이 줄보다 먼저 셸 주입 또는 서비스의 .env 로딩을 완료한다.
settings = get_settings()
app = FastAPI()

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)

# 마지막에 추가하여 CORS 사전 요청도 공통 로그로 확인한다.
app.add_middleware(RequestLoggingMiddleware)
```

이미 CORS가 있으면 기존 등록을 조정한다. 동일한 미들웨어나 오류 처리기를 중복 등록하지 않는다. `get_settings()`의 origin 값은 설정일 뿐이며 위처럼 CORS 미들웨어에 전달해야 적용된다. 프론트가 응답의 요청 ID를 읽으려면 `expose_headers`가 필요하다.

정상 요청·처리된 예외·사전 요청의 CORS는 서비스에서 확인한다. 예기치 않은 500은 FastAPI의 바깥쪽 오류 미들웨어에서 응답할 수 있으므로, 그 응답에도 CORS가 필요하면 서비스 담당자가 전체 ASGI 앱을 CORS로 감싸는 구성까지 검토·검증한다. 위 기본 등록만으로 모든 미처리 500의 CORS를 보장하지는 않는다.

## 4. 인증과 권한

### 사용자 정보

`CurrentUser`는 검증된 JWT에서 만든 읽기 전용 dataclass다. 딕셔너리가 아니므로 `user["team_id"]` 대신 `user.team_id`로 접근한다.

- `user_id`: 양의 정수. Java JWT의 문자열 `sub`를 변환한 값.
- `username`: 사용자 이름.
- `role`: `member` 또는 `team_admin`.
- `team_id`: 양의 정수 또는 팀 미가입을 나타내는 `None`.
- `team_type`: `dev`, `rnd` 또는 미가입 시 `None`.
- `level`: `L1`, `L2`, `L3`.
- `view`: `dev`, `rnd`.
- `id`: `user_id`의 문자열 별칭. 기존 음성 저장소의 소유자 식별에 사용한다.

JWT는 `iss/sub/username/role/team_id/team_type/level/view/iat/exp`를 포함해야 한다. 팀 미가입도 `team_id`와 `team_type`을 생략하지 않고 둘 다 `null`로 발급한다. 서명·허용 알고리즘·발급자·만료와 claim 형식이 검증되어야 사용자를 반환한다.

Python은 회원 DB를 조회하지 않는다. 역할·팀은 토큰 발급 시점 정보이며, Java의 프로필 수정·팀 가입 응답에서 새 토큰을 받으면 클라이언트가 교체해야 한다. 이 패키지에는 토큰 블랙리스트나 즉시 로그아웃 무효화 기능이 없다.

### 라우터에 의존성 연결

```python
from fastapi import APIRouter, Depends

from referoom_common import (
    CurrentUser,
    require_admin,
    require_team,
    verify_token,
)

router = APIRouter()


@router.get("/auth-example/me")
def me(user: CurrentUser = Depends(verify_token)):
    return {"user_id": user.user_id, "team_id": user.team_id}


@router.get("/auth-example/team")
def team(user: CurrentUser = Depends(require_team)):
    return {"team_id": user.team_id}


@router.get("/auth-example/admin")
def admin(user: CurrentUser = Depends(require_admin)):
    return {"team_id": user.team_id, "role": user.role}
```

위 경로는 설명용이며 실제 서비스에 추가할 필수 API가 아니다. 기존 RAG·음성 경로에 의존성을 적용한다.

- `verify_token`: 로그인 여부만 확인. 정상 토큰이면 팀 미가입도 통과.
- `require_team`: 로그인 + 팀 가입 확인. 미가입은 `403 NO_TEAM`.
- `require_admin`: 로그인 + 팀 가입 + `team_admin` 확인. 일반 팀원은 `403 FORBIDDEN`.

`Depends(require_team)`처럼 함수 자체를 전달한다. `Depends(require_team())`처럼 직접 실행하지 않는다. 검색 범위는 검증된 `user.team_id`를 사용하고, 요청의 team ID나 `view`로 접근 권한을 정하지 않는다. 의존성만 붙였다고 저장소의 팀 필터링까지 자동 적용되는 것은 아니다.

인증 순서는 다음과 같다.

1. `Authorization: Bearer <accessToken>` 헤더가 있으면 해당 토큰만 검증한다.
2. 헤더가 없을 때만 `ACCESS_TOKEN` 쿠키로 대체한다.
3. 잘못된 헤더·중복 헤더·변조 토큰을 정상 쿠키로 우회하지 않는다.

Vue는 현재 계약대로 Bearer와 `credentials: "omit"`을 사용한다. 쿠키 방식을 별도로 사용할 때만 클라이언트의 credentials와 서비스 CORS를 함께 맞춘다. Swagger에는 `bearerAuth`가 표시되며 로그인 응답의 토큰 문자열만 넣는다. 쿠키 입력창은 제공하지 않는다.

## 5. RAG 담당자 적용 지점

확인한 RAG 구현 브랜치는 `app/rag/auth_stub.py`와 자체 `app/rag/errors.py`를 사용한다. 다음을 한 묶음으로 적용한다.

1. 서비스 가상환경에 패키지를 설치하고 Java와 같은 `JWT_SECRET`을 주입한다.
2. `app/rag/deps.py`에서 인증 import를 아래 코드로 교체한다. 기존 검색 저장소 선택 분기는 유지한다.

```python
from referoom_common import CurrentUser, require_team
```

3. `app/rag/errors.py`의 자체 예외·처리기를 아래처럼 공통 항목을 다시 내보내는 코드로 교체할 수 있다. 그러면 기존 `from app.rag.errors import ApiError` 경로를 유지하면서 실제 클래스는 공통 항목으로 통일된다.

```python
from referoom_common import ApiError, register_error_handlers

__all__ = ["ApiError", "register_error_handlers"]
```

4. `app/main.py`에서 공통 예외 처리·로깅을 한 번씩 등록하고 CORS에 `X-Request-Id` 노출을 추가한다. 기존 RAG 라우터 등록을 유지한다.
5. `/rag-query`의 `Depends(require_team)`, 실제 저장소의 `user.team_id` 필터, 토큰 사용량 기록을 확인한다. 데이터 라우터도 기능에 맞게 `require_team` 또는 `require_admin`을 적용한다.

기존 `ApiError`와 공통 `ApiError`는 이름이 같아도 다른 클래스다. 인증만 교체하고 예외 처리기를 그대로 두면 인증 실패가 500으로 처리될 수 있다. 모든 오류 발생 지점과 처리기가 같은 공통 클래스를 사용하도록 맞춘다. 인증·저장소 스텁으로 성공한 응답은 실제 검색 E2E 검증과 구분한다.

## 6. 음성 담당자 적용 지점

현재 음성 코드는 공통 `require_team` 연결을 기다리는 라우터 팩토리가 준비되어 있다. 기존 `app/main.py`의 app·lifespan·환경 로딩을 유지하고 공통 예외·로그를 등록한 다음, 라우터 등록 위치에 다음 코드를 적용한다.

```python
from referoom_common import require_team

from app.routers.audio import create_audio_router
from app.routers.stt import create_stt_router
from app.routers.tts import create_tts_router

app.include_router(create_stt_router(require_team))
app.include_router(create_tts_router(require_team))
app.include_router(create_audio_router(require_team))
```

기존 음성 라우터는 `current_user.id`를 문자열 소유자 ID로 사용한다. 공통 `CurrentUser.id`가 이를 지원한다. 과거 쿠키 전용 라우터를 함께 등록해 같은 경로를 중복 제공하거나 인증을 우회하지 않는다.

현재 라우터에서 직접 반환하는 `JSONResponse({"detail": ..., "code": ...})`는 공통 예외 처리기가 다시 변환하지 않는다. 기존 서비스 오류 코드는 유지되고 요청 로그는 남는다. Pydantic 검증 오류·인증 예외는 공통 처리기로 처리된다.

후속 음성→RAG 요청에도 검증 가능한 사용자 Bearer 토큰을 전달해야 한다. `CurrentUser`는 토큰 원문을 포함하지 않으므로 `user.id`를 토큰처럼 보내면 안 된다. `/voice-qa`와 STT→RAG→TTS 연결은 별도 서비스 구현이며 위 등록 코드로 자동 완성되지 않는다.

## 7. 공통 예외 처리

서비스에서 의도한 오류는 다음처럼 발생시킨다.

```python
from referoom_common import ApiError


def require_ready(ready: bool) -> None:
    if not ready:
        raise ApiError(
            503,
            "NOT_READY",
            "검색 준비 중입니다. 잠시 후 다시 시도해 주세요.",
        )
```

HTTP 상태 503과 함께 아래 형식을 반환한다.

```json
{"detail":"검색 준비 중입니다. 잠시 후 다시 시도해 주세요.","code":"NOT_READY"}
```

- 무인증·잘못된 토큰: `401 UNAUTHORIZED`.
- 만료 토큰: `401 TOKEN_EXPIRED`.
- 팀 미가입: `403 NO_TEAM`.
- 관리자 권한 부족: `403 FORBIDDEN`.
- Pydantic 입력 검증 실패: `422 VALIDATION_ERROR`, 입력 원문 비노출.
- 예상하지 못한 예외: `500 INTERNAL_ERROR`, 내부 예외 내용 비노출.

401에는 `WWW-Authenticate: Bearer`가 붙는다. 로깅 미들웨어가 요청 ID를 설정한 경우 오류 응답에도 `X-Request-Id`가 붙는다. Java의 `{ok:false,error,code}`와 Python의 `{detail,code}`는 서로 다른 기존 계약이다.

`ApiError`의 detail은 그대로 클라이언트에 전달되므로 사용자에게 공개할 문장만 넣는다. `str(provider_exception)`이나 질문 원문을 무조건 넣지 않는다. 일반 `HTTPException`은 상태와 헤더를 유지하지만 detail은 일반 문구로 바뀐다. 서비스 고유 코드·메시지가 필요하면 `ApiError`를 사용한다.

## 8. 요청 로그와 토큰 사용량

`RequestLoggingMiddleware`는 HTTP 요청 완료 시 `referoom_common.access` 로거로 JSON 한 줄을 기록한다. 아래 값은 형식을 보여주는 가상 예시이며 실측 결과가 아니다.

```json
{"ts":"2026-10-24T00:00:00.000+00:00","request_id":"example-001","path":"/rag-query","status":200,"latency_ms":123.45,"user_id":101,"team_id":7,"in_tok":120,"out_tok":35}
```

- `ts`: 요청 시작 시각, UTC.
- `request_id`: 정상 단일 `X-Request-Id`를 유지하거나 새 UUID hex 생성. 허용 형식은 영문·숫자로 시작하고 영문·숫자·`.`·`_`·`:`·`-`로 이루어진 1~64자다. 누락·중복·잘못된 값은 교체한다.
- `path`: `/audio/{audio_id}` 같은 라우트 템플릿. 매칭되지 않으면 `<unmatched>`.
- `status`: 실제 응답 시작 상태. 그 전에 예외가 나면 500.
- `latency_ms`: ASGI 요청 처리가 끝날 때까지의 경과 시간. 스트리밍은 스트림 종료까지 포함하며 첫 토큰 시간과 다르다.
- `user_id/team_id`: JWT 검증이 기록한 요청 상태. 인증 전 실패는 `null`, 미가입 팀은 `null`.
- `in_tok/out_tok`: 서비스가 기록한 실제 입력·출력 토큰 수. 미기록·잘못된 값은 `null`, 실제 측정한 0은 `0`.

인증 성공 시 사용자·팀 ID는 자동 기록된다. **LLM 토큰 수는 공통 모듈이 계산하지 않는다.** RAG 담당자가 API usage를 읽어 `request.state`에 넣어야 한다. 여러 번 모델을 호출했다면 합산 기준을 정해 실제 값을 기록한다. 측정하지 못한 값을 0으로 대체하지 않는다.

RAG 라우터에서 다음처럼 예외 경로까지 고려해 기록할 수 있다. 기존 함수의 해당 부분에 적용하는 예시다.

```python
usage: dict = {}
try:
    resp = await run_in_threadpool(pipeline.run, req, user, usage)
    return resp
finally:
    request.state.in_tok = usage.get("in_tok")
    request.state.out_tok = usage.get("out_tok")
```

이 조각의 `request/req/user/pipeline/run_in_threadpool`은 기존 RAG 라우터의 객체를 사용한다. 모델 호출 중 실패한 경우에도 provider가 usage를 제공한 범위만 기록한다. STT·TTS만 실행한 요청에서 LLM usage가 없으면 그대로 `null`이다. 이 모듈은 STT 시간·TTS 문자 수·API 비용을 자동 집계하지 않는다.

질문·음성 원문·JWT·비밀키·사용자 이름·쿼리 문자열은 공통 액세스 로그에 넣지 않는다. 응답 본문을 버퍼링하거나 요청 본문을 읽지 않으므로 음성 파일·스트리밍 응답을 그대로 전달한다. ASGI 예외는 삼키지 않는다. Uvicorn 등 다른 서버·애플리케이션 로거의 설정은 별도로 확인한다.

## 9. 공통 모듈 테스트

저장소 루트에서 Python 3.11 이상의 활성화된 가상환경으로 실행한다. 테스트 의존성을 추가로 설치한다.

```bash
python -m pip install -e "./common-py[dev]"
python -m pytest -q common-py/tests
```

common-py 폴더에서 실행하려면 다음과 같다.

```bash
cd common-py
python -m pip install -e ".[dev]"
python -m pytest -q tests
```

테스트는 매번 임시 키·가상 JWT를 만들고 FastAPI TestClient를 사용한다. 실제 `.env`·회원 DB·Java 서버·LLM·Whisper·TTS·외부 네트워크가 필요하지 않으며 운영 키를 사용하지 않는다.

2026-10-24 검증 결과는 **125개 통과**다.

- `test_auth.py`: 74개. Bearer·쿠키·변조/만료/claim·팀/관리자·환경 설정.
- `test_errors.py`: 30개. 서비스/HTTP/입력 오류, 500 비노출, 요청 ID.
- `test_logging_mw.py`: 21개. JSON 필드·토큰 수·민감정보 비노출·동시 요청·스트리밍.

검증 환경은 Python 3.11.15, FastAPI 0.162.0, Starlette 1.9.0, httpx 0.28.1, PyJWT 2.15.1, pytest 9.1.1이다. Starlette TestClient의 httpx 사용 중단 예고가 1건 있었고 실패는 없었다. 각 서비스의 전체 고정 의존성 조합과 모델 실행까지 검증한 결과는 아니다.

## 10. 각 서비스에 적용한 뒤 확인할 사항

1. 실제 Java 로그인 응답의 accessToken으로 보호 API가 통과한다. Swagger에는 Bearer 접두사 없이 토큰 문자열만 넣는다.
2. 무토큰·잘못된 서명·만료 토큰은 401, 미가입 사용자는 `403 NO_TEAM`, 일반 팀원의 관리자 접근은 `403 FORBIDDEN`이다.
3. RAG 검색은 검증된 팀 범위로 제한되고, 다른 팀 자료는 검색·원문 API 모두에서 차단된다. 설명 `view` 변경으로 권한이 바뀌지 않는다.
4. 정상 요청·입력 오류·서비스 오류가 기존 API 계약을 유지하고 요청 ID로 응답과 로그를 연결할 수 있다.
5. 프론트 origin의 OPTIONS와 실제 Bearer 요청이 통과하고 브라우저가 `X-Request-Id`를 읽을 수 있다.
6. RAG usage가 로그에 남으며 알 수 없는 사용량과 실제 0이 구분된다. 질문·토큰 원문은 로그에 남지 않는다.
7. 음성 모델이 준비되면 STT·TTS·인증 오디오 다운로드를 확인하고, 다른 사용자 오디오·만료 오디오를 읽을 수 없는지 확인한다.

공통 모듈 테스트 통과와 실제 Java→RAG·음성 서비스 E2E 성공은 별도다. 배포 시에는 컨테이너의 패키지 설치·환경 주입·CORS·모델 준비 상태까지 각 서비스 담당자와 함께 확인한다.
