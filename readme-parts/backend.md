## 백엔드: Java 인증 서버 · 공통 Python 모듈

레퍼룸의 회원·팀 관리, JWT 발급, Python 서비스의 인증·권한·오류·요청 로그를 담당한다. 이 문서는 2026-10-24 현재 코드와 DEV_01·DEV_05 및 최종 폴더 소유권 기준을 반영한다.

### 1. 구성과 담당 범위

서비스 연결 구조는 다음과 같다. Python 앱에 공통 모듈을 적용하는 작업은 각 서비스 담당자가 진행한다.

```text
Vue ── 로그인·회원·팀 API ──▶ Spring Boot ──▶ MariaDB(users, teams)
 │                              │
 │◀──────── JWT 발급 ────────────┘
 ├── Bearer JWT ──▶ FastAPI RAG ──▶ 검색·LLM
 └── Bearer JWT ──▶ FastAPI 음성 ──▶ STT·TTS
                     └─ 두 Python 서비스가 referoom_common을 사용
```

Java는 JWT를 발급하며 모든 AI 요청을 중계하는 프록시가 아니다. Vue가 각 서비스 API를 직접 호출하고, AI 서비스는 같은 서명 비밀키로 JWT를 검증한다. Python 서비스는 회원 테이블을 조회하지 않는다.

- `auth-server/`: Spring Boot 인증 API 11개, JPA 엔티티·저장소, JWT·CORS·Swagger, Dockerfile·환경변수 예시.
- `common-py/`: 설치 가능한 `referoom-common` 패키지와 공통 모듈 테스트.
- `db/migrations/001_users.sql`, `002_teams_users.sql`, `900_dev_seed.sql`: 회원·팀 DB 최초 초기화와 개발 시드.
- `scripts/e2e_check.sh`: 실제 Java 로그인과 RAG 인증·출처·팀 격리 점검.
- `scripts/ops_report.py`: 공통 JSON 로그의 지연·토큰·비용 집계.

RAG·데이터·음성·프론트 코드의 연결은 각 담당자가 진행한다. 루트 Compose·환경변수 예시·README 취합은 배포 담당 범위이며, 이 문서 작성만으로 전체 배포가 완료된 것은 아니다.

**주요 구현 선택**

- 원본 `SimpleAuthServer.java`는 참고본으로 유지하고 실행 진입점은 `workplace.AuthServerApplication`을 사용한다.
- Spring Boot `4.0.8`, Gradle Wrapper `9.0.0`, MariaDB JDBC `3.5.6`, springdoc `3.0.3`을 사용한다. Java 소스·타깃 설정은 17이며, 현재 실행·Docker 검증 환경은 JDK/JRE 21이다.
- Controller → Service → Repository/JPA 구조이며 DTO·엔티티 변환 빌더는 Converter에 둔다. Enum은 `@Enumerated(EnumType.STRING)`으로 저장한다.
- Python 3.11 이상, FastAPI, PyJWT를 사용한다. 공통 모듈은 Whisper·LLM SDK·Uvicorn·FFmpeg를 설치하거나 실행하지 않는다.

### 2. 인증 서버 환경변수

명령은 별도 표시가 없으면 저장소 루트 `referoom/` 기준이다. 실제 비밀값은 Git에 올리지 않는다.

처음 설정할 때만 예시를 복사하고, 이미 `.env`가 있으면 유지한다.

```bash
cd auth-server
test -f .env || cp .env.example .env
```

`auth-server/.env`에서 `DB_PASSWORD`와 `JWT_SECRET`을 실제 값으로 채운다. 나머지 값도 자신의 DB·브라우저 주소에 맞춘다.

| 변수 | `.env.example` 값 | 용도 |
|---|---|---|
| `DB_HOST` | `localhost` | 호스트 실행 시 DB 주소 |
| `DB_PORT` | `53301` | 현재 로컬 Docker DB의 호스트 공개 포트 |
| `DB_NAME` | `sql_db` | 미리 생성한 DB 이름 |
| `DB_USER` | `root` | DB 접속 계정 |
| `DB_PASSWORD` | 빈 값 | 해당 DB 계정의 실제 비밀번호 |
| `JWT_SECRET` | 빈 값 | Java·RAG·음성에 동일하게 주입할 비밀키 |
| `FRONTEND_URL` | `http://localhost:5174` | 프론트 주소 설정. 현재 JSON 로그인은 redirect를 반환하지 않음 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5174,http://localhost:8008` | 쉼표로 구분한 브라우저 Origin |

예시 파일의 값은 Spring 설정의 기본값이 아니다. 현재 `application.yml`의 DB·프론트 설정에는 `${변수명}`만 있으므로 프로세스에 값을 주입해야 한다. `.env` 파일을 만들기만 해서는 Spring Boot가 자동으로 읽지 않는다.

- 포트는 `application.yml`에서 8080이다. 변경 시 Spring 환경변수 `SERVER_PORT` 또는 `--server.port=18080`을 사용할 수 있다.
- JWT 계약은 `HS256`, issuer `simple-auth-server`, 유효기간 `3600`초다. Python 설정과 함께 유지한다.
- Java의 `AUTH_DEBUG` 전용 설정은 현재 구현하지 않았다. 필요 없는 환경변수를 추가하지 않는다.
- `open-in-view=false`, `show-sql=false`, `ddl-auto=update`, `spring.sql.init.mode=never`를 사용한다.
- `ddl-auto=update`는 현재 개인 개발 설정이다. SQL로 준비한 DB를 검증만 하려면 실행 환경에 `SPRING_JPA_HIBERNATE_DDL_AUTO=validate`를 주입한다. Java가 마이그레이션 SQL을 자동 실행하지는 않는다.

### 3. 로컬 실행과 빌드

현재 로컬 DB는 `voice-mini-mariadb` 컨테이너의 `127.0.0.1:53301 → 3306`, DB 이름은 `sql_db`다. 다른 개발자는 자신의 접속 정보로 바꾼다. 기존 DB가 있으면 새 컨테이너나 볼륨을 만들 필요가 없다.

```bash
docker ps -a --filter name=voice-mini-mariadb
docker start voice-mini-mariadb
```

`auth-server/`에서 JDK 21 환경을 확인하고, 작성한 `.env`를 주입해 실행한다.

```bash
java -version

set -a
source ./.env
set +a

bash ./gradlew :app:bootRun --no-configuration-cache
```

새 터미널에서 상태를 확인한다.

```bash
curl --fail-with-body http://localhost:8080/api/health
```

정상 응답은 `{"ok":true,"db":"up"}`이다. DB 쿼리 실패는 `503 NOT_READY`다. 서버 기동 자체가 DB 연결에 실패했다면 HTTP 응답을 받을 수 없으므로 기동 로그와 환경변수를 먼저 확인한다.

- Swagger UI: `http://localhost:8080/swagger-ui/index.html`
- OpenAPI JSON: `http://localhost:8080/v3/api-docs`

실행 JAR 빌드와 개별 실행은 `auth-server/`에서 다음과 같다. JAR 실행 전에도 위 환경변수 주입이 필요하다.

```bash
bash ./gradlew clean build --no-configuration-cache
java -jar app/build/libs/app-0.0.1-SNAPSHOT.jar
```

현재 Java 전용 자동 테스트 코드는 없다. Gradle 빌드 성공과 실제 API·DB·브라우저 연동 검증은 구분한다. 구형 `SimpleAuthServer`나 DB 예제 실행 작업을 Spring Boot 실행 명령 대신 사용하지 않는다.

### 4. DB 최초 초기화와 시드

**이미 JPA로 `users`, `teams`를 만든 현재 DB에는 001·002를 다시 실행하지 않는다.** 아래 SQL은 기존 테이블을 변환하는 버전 관리 마이그레이션이 아니라, 테이블이 없는 새 DB 최초 초기화용이다. DB 자체와 접속 계정은 먼저 준비한다.

1. `001_users.sql`: 확장된 `users` 테이블 생성. `team_id`는 아직 외래키 없이 생성.
2. `002_teams_users.sql`: `teams` 생성 후 `users.team_id` 외래키 연결.
3. `003_rag_tables.sql`: 데이터 담당이 제공하는 AI 데이터 스키마. 해당 파일의 준비 여부는 별도로 확인.
4. `900_dev_seed.sql`: 개발·데모용 팀과 계정 생성. 운영 환경에는 자동 적용하지 않는다.

새 DB에 001·002를 수동 적용할 경우, 저장소 루트에서 실행한다. `DB_HOST/DB_PORT/DB_USER/DB_NAME`은 먼저 `.env`에서 export해야 하며 비밀번호는 MariaDB 클라이언트 프롬프트에 입력한다. 터미널에 mysql 호환 클라이언트인 `mariadb` 명령이 필요하다.

```bash
mariadb --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" \
  --password "$DB_NAME" < db/migrations/001_users.sql

mariadb --host="$DB_HOST" --port="$DB_PORT" --user="$DB_USER" \
  --password "$DB_NAME" < db/migrations/002_teams_users.sql
```

시드가 필요한 개발 DB에서만 같은 방식으로 `900_dev_seed.sql`을 별도 적용한다. 001·002는 재실행용 `IF NOT EXISTS` 스크립트가 아니며, SQL 파일은 현재 실제 DB에 실행해 검증한 상태가 아니다.

시드 파일은 **개발팀·R&D팀 각각 관리자와 팀원 1명씩, 미가입 계정 1명을 포함한 2팀·5계정**으로 구성한다. 공통 비밀번호 `Demo-pass-1234!`, 개발팀 초대 코드 `RFDEV234`, R&D팀 초대 코드 `RFRND234`는 공개된 개발용 값이며 실제 서비스 자격 증명이 아니다. SQL 파일 수정만 완료한 상태로, 실제 DB 적용·로그인 검증은 아직 하지 않았다.

| 계정 | 역할 | 소속 | 수준 |
|---|---|---|---|
| `demo_admin` | `team_admin` | 개발 데모팀(`dev`) | `L2` |
| `demo_member` | `member` | 같은 개발 데모팀 | `L1` |
| `demo_rnd_admin` | `team_admin` | R&D 데모팀(`rnd`) | `L3` |
| `demo_rnd_member` | `member` | 같은 R&D 데모팀 | `L2` |
| `demo_solo` | `member` | 없음 | `L2` |

기존 아이디·코드는 덮어쓰지 않으며 ID는 자동 생성된다. 초대 코드 재발급 후 시드를 재실행하면 고정 코드의 팀이 추가될 수 있으므로 반복 초기화 용도로 사용하지 않는다.

모든 시드 계정의 `view_pref`는 NULL이며 개발팀의 기본 관점은 `dev`, R&D팀의 기본 관점은 `rnd`다. `demo_solo`는 미가입 기본 관점 `dev`를 사용한다. 팀 격리 E2E는 개발팀의 `demo_admin`과 R&D팀의 `demo_rnd_admin`을 사용할 수 있다. 데이터 담당자가 주 데모 논문을 개발팀에만 적재하고 R&D팀 라이브러리는 비워 둔다. `demo_solo`는 팀 미가입 권한 점검용이며 다른 팀 계정을 대신하지 않는다.

전체 Compose에서 DB 초기화 디렉터리를 마운트할 때는 배포 담당이 DB 생성 이름, 파일 순서와 900의 개발 환경 한정을 맞춘다. 초기화 스크립트는 빈 DB 볼륨에서만 자동 적용되며 기존 볼륨을 재시작한다고 다시 실행되지 않는다.

### 5. 인증 API 11개

JSON 요청은 `Content-Type: application/json`을 사용한다. 가입·로그인의 form-urlencoded 요청도 JSON으로 응답하며, 원본 HTML의 리다이렉트 흐름을 그대로 제공하지는 않는다.

| 메서드·경로 | 인증·권한 | 성공 | 주요 응답 |
|---|---|---|---|
| `POST /api/signup` | 공개 | 201 | `ok`, `teamId`, `role`, 생성 시 `inviteCode` |
| `POST /api/login` | 공개 | 200 | `ok`, `accessToken`, `tokenType`, `expiresIn`, `user` |
| `POST /api/logout` | 인증 불필요 | 200 | `ok:true`, 인증 관련 쿠키 삭제 |
| `GET /api/me` | Bearer | 200 | DB 최신 정보인 `user` |
| `PATCH /api/me/profile` | Bearer | 200 | `ok`, 새 `accessToken`, `user` |
| `GET /api/team` | Bearer + 팀 가입 | 200 | `team` 안의 `id/name/type/memberCount`, 관리자만 `inviteCode` |
| `POST /api/team/join` | Bearer + 팀 미가입 | 200 | `ok`, 새 `accessToken`, `user` |
| `GET /api/team/members` | Bearer + 팀 관리자 | 200 | `items`, `total` |
| `POST /api/team/invite-code/rotate` | Bearer + 팀 관리자 | 200 | `ok`, 새 `inviteCode` |
| `GET /api/auth/check` | Bearer 또는 헤더 없을 때 쿠키 | 200 | `ok`, `via:"jwt"`, `username`, `sub` |
| `GET /api/health` | 공개 | 200 | `ok:true`, `db:"up"` |

`GET /api/team`은 `{"team":{...}}`, `GET /api/me`는 `{"user":{...}}`로 감싼다. `user`에는 `id/username/displayName/role/level/view/team`이 있고 미가입이면 `team:null`이다. 팀원 목록의 공개 필드는 `id/username/displayName/role/level/view`다.

**회원가입 예시: 아래 값은 설명·테스트용이며 실행하면 DB에 계정을 생성한다.** 같은 아이디로 반복 가입하면 409다.

```json
{
  "username": "readme_admin",
  "password": "Example-pass-1234!",
  "displayName": "테스트 관리자",
  "level": "L2",
  "teamMode": "create",
  "teamName": "레퍼룸 테스트팀",
  "teamType": "dev"
}
```

- `username`: trim 후 4~50자, 중복 불가.
- `password`: 8자 이상이며 UTF-8 72바이트 이하. BCrypt cost 12로 저장.
- `level`: 생략 시 `L2`, 허용값 `L1/L2/L3`.
- `teamMode:"create"`: `teamName`, `teamType(dev/rnd)` 필요. 가입자는 `team_admin`.
- `teamMode:"join"`: 실제 `teamCode` 필요. 가입자는 `member`.
- `teamMode` 생략: 팀 없이 `member`로 가입. 가입 응답은 로그인 토큰을 발급하지 않으므로 이어서 로그인한다.

로그인과 프로필 변경 요청 예시는 다음과 같다.

```json
{"username":"readme_admin","password":"Example-pass-1234!"}
```

```json
{"level":"L3","view":"rnd"}
```

프로필의 두 필드는 각각 선택이지만 하나 이상은 있어야 한다. 현재 PATCH는 `displayName`을 수정하지 않는다. 수준·관점 변경은 팀이나 권한을 바꾸지 않는다.

팀 참여 요청은 `{"teamCode":"발급받은 실제 코드"}`이며 코드는 주변 공백 제거·대문자 정규화를 거친다. 한 사용자는 한 팀에만 가입한다. 초대 코드는 8자 영숫자로 생성되며, 재발급 후 이전 코드로 새로 참여할 수 없고 기존 팀원 소속은 유지된다.

**오류 응답**

Java는 `{"ok":false,"error":"사용자 안내","code":"UNAUTHORIZED"}`, Python은 `{"detail":"사용자 안내","code":"UNAUTHORIZED"}` 형식이다. 프론트는 두 형식을 모두 처리한다.

| HTTP | Java 주요 code | 상황 |
|---|---|---|
| 400 | `BAD_REQUEST` | 잘못된 요청 형식 |
| 401 | `INVALID_CREDENTIALS` | 로그인 정보 불일치 |
| 401 | `UNAUTHORIZED`, `TOKEN_EXPIRED` | 인증 정보 없음·오류 또는 만료 |
| 403 | `NO_TEAM`, `FORBIDDEN` | 팀 미가입 또는 팀·관리자 권한 불일치 |
| 404 | `TEAM_NOT_FOUND` | 초대 코드에 해당하는 팀 없음 |
| 409 | `CONFLICT`, `ALREADY_IN_TEAM` | 중복 아이디 또는 이미 팀 가입 |
| 422 | `VALIDATION_ERROR` | 입력 검증 실패 |
| 503 | `NOT_READY` | 헬스체크의 DB 쿼리 실패 |
| 500 | `INTERNAL_SERVER_ERROR` | 예상하지 못한 내부 오류 |

**토큰·쿠키·프론트 연결**

- JWT claim은 `iss/sub/username/role/team_id/team_type/level/view/iat/exp`다. `sub`는 문자열 사용자 ID, `team_id`는 정수 또는 null이다. 미가입은 `team_id/team_type` 둘 다 null이며 키를 생략하지 않는다.
- role은 `member/team_admin`, team_type과 view는 `dev/rnd`, level은 `L1/L2/L3`다. 기본 view는 개인 선택 → 팀 유형 → `dev` 순서다.
- 로그인은 JSON 토큰과 `ACCESS_TOKEN` HttpOnly·SameSite=Lax·Path=/ 쿠키를 발급한다. Secure는 서버가 인식한 HTTPS 요청 여부에 따른다.
- 현재 Java의 쿠키 대체 인증은 **GET `/api/auth/check`에만** 허용한다. `/api/me`, `/api/team` 등은 Bearer가 필요하다. Python common-py는 적용한 보호 경로에서 헤더가 없으면 쿠키를 사용한다.
- Authorization 헤더가 있으면 그 값을 검증하고 잘못된 헤더를 정상 쿠키로 우회하지 않는다.
- Swagger 인증창은 `bearerAuth` 하나다. 로그인 응답의 토큰 문자열만 입력하고 `Bearer `는 붙이지 않는다.
- Vue 요청은 Bearer와 `credentials:"omit"`을 사용한다. 프로필 변경·팀 참여 후 응답의 `accessToken`으로 기존 토큰을 교체한다.
- Java 팀 조회·관리 API는 JWT와 DB 소속을 대조하며 관리자 기능은 양쪽 역할도 확인한다. Python 권한은 토큰 발급 시점 정보다.
- 로그아웃은 쿠키·보안 컨텍스트를 정리한다. 프론트가 보관한 토큰도 삭제해야 한다. 토큰 블랙리스트나 refresh token은 없으며 이미 발급한 Bearer는 만료까지 유효할 수 있다.
- 프론트 연동 시 `VITE_AUTH_URL=http://localhost:8080`, `VITE_USE_MOCK=false`와 실제 Origin을 맞춘다. Java CORS는 `/api/**`에 GET/POST/PATCH/OPTIONS와 Authorization·Content-Type·X-Request-Id를 허용한다. Python도 각 서비스에서 CORS를 연결해야 한다.

### 6. common-py 설치와 적용

설치 이름은 `referoom-common`, import 이름은 `referoom_common`이다. 상세 서비스별 적용 지점·호환 주의사항은 `common-py/README.md`에 있다. 공통 모듈은 백엔드만 변경하며 RAG·음성 담당자가 자신의 앱에 적용한다.

서비스 가상환경을 활성화한 뒤 **해당 서비스 폴더에서** 설치한다.

```bash
python -m pip install -e ../common-py
python -m pip check
python -c "from referoom_common import CurrentUser, require_team; print('common-py import OK')"
```

이 명령은 서비스 자체 의존성 설치를 대체하지 않는다. RAG는 담당자가 제공한 `requirements-data.txt`, `requirements-rag.txt`를, 음성은 `requirements.txt`를 별도로 설치한다. 현재 브랜치에 파일이 없으면 해당 담당 변경을 반영한 뒤 진행하며 빈 requirements를 새로 만들지 않는다. 패키지는 각 가상환경에 각각 설치한다.

Python에는 `JWT_SECRET`과 `CORS_ALLOWED_ORIGINS`를 주입한다. Java와 **동일한 비밀키 문자열**을 사용하며 따로 Base64 디코딩하지 않는다. issuer·알고리즘은 공통 설정에 고정돼 있으므로 `JWT_ISSUER/JWT_ALGORITHM` 환경변수를 추가해도 바뀌지 않는다.

common-py는 `.env`를 자동 로딩하지 않는다. 서비스 `.env`를 셸에서 export하거나 서비스 설정 조회 전에 로딩한다. `get_settings()`는 첫 조회를 캐시하므로 변경 후 서버를 재시작한다.

**FastAPI 등록 최소 예시**

아래 코드는 연결 방법을 설명한다. 기존 서비스에서는 새 app을 만들지 말고 현재 app에 등록 부분을 적용하며 기존 lifespan·모델·라우터를 유지한다. 미들웨어·CORS·예외 처리기를 중복 등록하지 않는다.

```python
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from referoom_common import (
    ApiError, CurrentUser, RequestLoggingMiddleware,
    get_settings, register_error_handlers, require_admin, require_team,
)

# 서비스 환경변수 로딩 이후 실행한다.
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
app.add_middleware(RequestLoggingMiddleware)


# 설명용 경로다. 실제 RAG·데이터·음성 경로에 같은 의존성을 적용한다.
@app.get("/example/team")
def team_example(user: CurrentUser = Depends(require_team)):
    return {"team_id": user.team_id}


@app.get("/example/admin")
def admin_example(user: CurrentUser = Depends(require_admin)):
    return {"team_id": user.team_id, "role": user.role}


def ensure_ready(ready: bool):
    if not ready:
        raise ApiError(503, "NOT_READY", "검색 준비 중입니다.")
```

- `verify_token`: 로그인 확인. 팀 미가입도 통과.
- `require_team`: 로그인·팀 가입 확인. 미가입은 `403 NO_TEAM`.
- `require_admin`: 팀 관리자 확인. 일반 팀원은 `403 FORBIDDEN`.
- `CurrentUser`는 읽기 전용 dataclass다. `user.user_id`는 int, `user.id`는 문자열 별칭이며 `username/role/team_id/team_type/level/view`를 제공한다. dict 인덱싱 대신 속성을 사용한다.
- 검색·자료 접근 범위는 검증한 `user.team_id`로 제한한다. 의존성만 등록해도 검색 저장소 필터가 자동 적용되는 것은 아니다.
- 기존 RAG의 자체 `ApiError`와 공통 `ApiError`를 섞지 않는다. 발생 지점·처리기를 공통 클래스로 통일해야 한다. 스텁 인증·검색 성공은 실제 통합 성공과 구분한다.
- 음성 담당자는 기존 `create_stt_router(require_team)`, `create_tts_router(require_team)`, `create_audio_router(require_team)` 팩토리를 등록할 수 있다. `/voice-qa`와 RAG 호출은 별도 구현이며 CurrentUser에는 토큰 원문이 없다.
- 공통 예외는 401·403·422와 안전한 500 응답을 제공한다. 서비스 준비 실패·타임아웃은 서비스가 `ApiError(503, "NOT_READY" 또는 "UPSTREAM_TIMEOUT", 공개 가능한 문장)`로 발생시킨다. SDK 예외를 자동으로 503으로 변환하지 않는다.
- 예기치 않은 500 응답의 CORS까지 필요한 경우 전체 ASGI 앱을 CORS로 감싸는 구성과 브라우저 동작을 서비스별로 확인한다.

**요청 로그**

```json
{"ts":"2026-10-24T00:00:00.000+00:00","request_id":"example-001","path":"/rag-query","status":200,"latency_ms":123.45,"user_id":101,"team_id":7,"in_tok":120,"out_tok":35}
```

위 값은 형식 설명용 가상 예시다. 실제 미들웨어는 `referoom_common.access` 로거의 StreamHandler(기본 stderr)에 한 요청당 JSON 한 줄을 남긴다. 로그 파일로 수집할 때 stderr도 포함해야 한다.

- 요청 ID를 생성·전파하고 `X-Request-Id` 응답 헤더에 넣는다. 경로는 매칭된 라우트 템플릿 또는 `<unmatched>`이며 지연은 스트리밍 종료를 포함한 처리 시간이다.
- 사용자·팀 ID는 인증 성공 시 기록한다. 인증 전 실패·미가입 팀은 null이다.
- 모델 호출 토큰은 서비스가 `request.state.in_tok/out_tok`에 기록해야 한다. 알 수 없는 값은 null, 실제 0은 0으로 유지한다. 예외 경로에서도 측정 가능한 usage는 기록한다.
- 질문·답변·음성 원문·JWT·비밀키를 기록하지 않는다. Uvicorn·SDK·애플리케이션의 다른 로거는 별도 점검 대상이다.

Docker의 Python 서비스는 **저장소 루트 build context**에서 `common-py/`를 복사하고 일반 설치한다. 서비스별 Dockerfile의 다른 COPY 경로도 해당 context에 맞춰야 한다.

```dockerfile
COPY common-py/ /opt/referoom-common/
RUN python -m pip install --no-cache-dir /opt/referoom-common
```

### 7. 인증 서버 Docker 실행

저장소 루트에서 빌드한다. 현재 Dockerfile은 auth-server 폴더를 context로 사용하며 Temurin 21 JDK 빌드 → 21 JRE 실행, 비루트 app 사용자 구성이다.

```bash
docker build --tag referoom-auth:local ./auth-server
```

다음은 **macOS Docker Desktop + 기존 호스트 공개 DB 포트 53301**을 사용하는 별도 포트 실행 예시다. `.env`를 셸에서 읽고 변수 이름으로 Docker에 전달하므로 셸용 따옴표가 비밀번호 값에 포함되는 문제를 피한다.

```bash
(
  set -a
  source ./auth-server/.env
  set +a

  docker run --rm --name referoom-auth-local \
    --publish 127.0.0.1:18080:8080 \
    --env DB_HOST=host.docker.internal \
    --env DB_PORT=53301 \
    --env DB_NAME --env DB_USER --env DB_PASSWORD --env JWT_SECRET \
    --env FRONTEND_URL --env CORS_ALLOWED_ORIGINS \
    --env SPRING_JPA_HIBERNATE_DDL_AUTO=validate \
    --env SPRING_SQL_INIT_MODE=never \
    referoom-auth:local
)
```

```bash
curl --fail-with-body http://localhost:18080/api/health
```

종료할 때는 별도 터미널에서 `docker stop referoom-auth-local`을 실행한다. `--rm` 옵션으로 해당 임시 컨테이너만 삭제되며 DB 컨테이너·볼륨은 유지된다.

전체 Compose에서는 DB 호스트를 Compose 서비스명(예: `db`), 포트를 내부 포트 `3306`으로 바꾼다. 브라우저의 API 주소와 컨테이너 내부 통신 주소는 구분한다. 공통 Python 설치가 필요한 서비스와 auth-server의 build context도 서로 다르다. 루트 Compose 통합·전체 healthcheck·영속 볼륨 검증은 배포 담당과 진행한다.

### 8. 테스트 방법

#### 8.1 common-py 자동 테스트

저장소 루트에서 전용 Python 3.11 가상환경을 사용한다. 이미 테스트 환경이 있으면 생성은 생략한다.

```bash
python3.11 -m venv /tmp/referoom-common-tests
source /tmp/referoom-common-tests/bin/activate
python -m pip install -e "./common-py[dev]"
python -m pytest -q common-py/tests
```

임시 키·가상 JWT·FastAPI TestClient로 검증하므로 실제 DB·Java·LLM·음성 모델은 사용하지 않는다. 인증/권한/설정, 공통 예외 처리, 요청 로그·스트리밍·동시 요청을 점검한다. 2026-10-24 기록된 결과는 **125개 통과**이며 각 서비스 모델·전체 의존성 조합의 검증과는 별도다.

#### 8.2 Swagger·프론트 수동 점검

1. `/api/health`의 200·`db:up`을 확인한다.
2. 팀 생성 가입 → 로그인 → `bearerAuth`에 토큰 입력 → `/api/me`, `/api/team`을 확인한다.
3. 프로필 PATCH 후 새 토큰으로 인증을 교체하고 수준·관점을 확인한다.
4. 실제 초대 코드로 일반 팀원 가입과 기존 미가입 계정의 `/api/team/join`을 각각 확인한다.
5. 관리자 팀원 목록·코드 재발급 200, 일반 팀원 403, 미가입 팀 조회 403을 확인한다.
6. 재발급 후 이전 코드 404, 새 코드 참여 성공, 기존 팀원 소속 유지를 확인한다.
7. 무토큰·잘못된 토큰 401, 중복 아이디 409, 검증 실패 422를 확인한다.
8. Java 쿠키 인증은 `/api/auth/check`에서 확인한다. Swagger는 쿠키 입력창을 제공하지 않는다.
9. Vue의 mock을 끄고 가입·로그인·프로필 변경·팀 참여·로그아웃과 새로고침 동작을 확인한다. 로그아웃 후 브라우저 토큰 삭제·보호 화면 접근 차단도 확인한다.

DB 중지 시 503은 별도 격리된 테스트 DB에서 확인한다. 기존 팀 작업용 DB를 멈추는 기본 테스트 절차로 사용하지 않는다.

#### 8.3 실제 Java → RAG E2E

`scripts/e2e_check.sh`는 **실제 서버와 유료 모델 호출이 발생할 수 있는 점검**이다. Bash·curl·jq·mktemp와 다음 준비가 필요하다.

- Java `/api/health`와 RAG `/health`가 정상이어야 한다.
- 주 계정은 팀에 가입하고, 지정한 PDF가 그 팀에만 적재되어 있어야 한다.
- 시드를 적용한 테스트 DB라면 주 계정은 개발팀 `demo_admin`, 다른 팀 계정은 R&D팀 `demo_rnd_admin`을 사용한다. 두 계정의 실제 소속도 확인한다. `demo_solo`는 미가입 계정이므로 팀 격리 계정을 대신할 수 없다.
- 실제 숫자 paper ID, 그 논문에서 답할 수 있는 질문, 전체 라이브러리 밖 질문을 준비한다.
- common-py 적용과 실제 저장소·LLM 준비를 끝내고, 아래 자리표시자를 실제 테스트 값으로 바꾼다. JWT_SECRET을 이 스크립트에 줄 필요는 없다.

저장소 루트에서 환경을 준비한다. `read -s`에서는 입력 문자가 화면에 보이지 않는다.

```bash
export AUTH_URL=http://localhost:8080
export RAG_URL=http://localhost:8001
export TIMEOUT_SECONDS=60
export E2E_USERNAME=demo_admin
export E2E_OTHER_USERNAME=demo_rnd_admin
export E2E_PAPER_ID='실제_숫자_ID로_교체'
export E2E_QUESTION='지정한 논문에서 답할 수 있는 실제 질문으로 교체'
export E2E_OUT_OF_SCOPE_QUESTION='라이브러리 전체에 근거가 없는 실제 질문으로 교체'

printf '주 계정 비밀번호: '
read -r -s E2E_PASSWORD
printf '\n다른 팀 계정 비밀번호: '
read -r -s E2E_OTHER_PASSWORD
printf '\n'
export E2E_PASSWORD E2E_OTHER_PASSWORD

bash scripts/e2e_check.sh
e2e_exit_code=$?
unset E2E_PASSWORD E2E_OTHER_PASSWORD
printf 'E2E 종료 코드: %s\n' "$e2e_exit_code"
```

검사 순서는 ① Java 로그인 ② 무토큰·잘못된 토큰 RAG 401 ③ 정상 질문의 답변·출처·지정 논문 페이지 ④ 문서 밖 질문의 handoff·빈 출처 ⑤ 다른 팀에서 같은 논문·질문에 자료 비노출이다. 주 계정에서 먼저 답변 가능한지 확인한 후 팀 격리를 검사한다.

성공은 종료 코드 0, 검사 실패는 1이다. 실제 요청 본문·토큰은 제한된 임시 파일로 처리하고 종료 시 삭제한다. 계정·논문을 자동 생성하거나 로그아웃하지는 않는다. 답변 의미 정확성, 출처 내용 일치, LLM 미호출 여부·브라우저 UI·선택 음성은 별도로 확인한다.

#### 8.4 운영 로그 리포트

Python 3.11 표준 라이브러리만 사용한다. 실제로 수집한 공통 JSON 로그 파일을 입력한다. 아래 `/tmp/referoom-rag.log`는 사용자가 준비할 입력 경로이며 저장소에 포함된 파일이 아니다.

```bash
python3 scripts/ops_report.py /tmp/referoom-rag.log \
  --service rag > /tmp/referoom-ops-report.md
```

Compose 통합 후에는 실제 서비스명을 확인하여 다음처럼 수집할 수 있다. `rag`는 Compose 서비스명 예시다. `--timestamps`처럼 JSON 앞에 별도 시각을 붙이는 옵션은 사용하지 않는다.

```bash
docker compose logs --no-color --no-log-prefix --since 1h rag \
  | python3 scripts/ops_report.py --service rag \
  > /tmp/referoom-ops-report.md
```

서비스·경로별 요청 수, 평균/최대/p95 지연, 4xx/5xx 비율, 평균 토큰, 측정 건수, 측정분 비용·요청당 비용과 민감정보 의심 패턴을 출력한다. p95는 정렬 후 `ceil(N×0.95)`번째 값이고 지연·오류율은 모든 상태 코드를 포함한다.

비용이 필요하면 `LLM_PRICE_IN`, `LLM_PRICE_OUT`에 **실제로 사용하는 모델의 100만 토큰당 USD 단가**를 함께 export한다. 단가 확인 날짜·모델명·로그 수집 기간은 리포트 제출 시 별도로 기록한다. 스크립트가 요금표를 자동 조회하지 않으며 여러 모델·할인 단가가 섞인 로그는 나누어 집계해야 한다.

월 예상 비용 예시는 위 단가를 설정한 뒤 실행한다. 아래는 4명·1인 하루 10질문·월 20일, 월 임베딩/서버 추가 비용을 각각 0 USD로 가정한 예시이며 팀 환경에 맞게 바꾼다.

```bash
python3 scripts/ops_report.py /tmp/referoom-rag.log \
  --service rag --forecast-path /rag-query \
  --team-members 4 --daily-questions 10 --workdays 20 \
  --embedding-usd 0 --server-usd 0 \
  > /tmp/referoom-ops-report.md
```

- 입력·출력 토큰이 둘 다 측정된 요청만 토큰 평균·비용에 사용하며 `측정 건수/전체 요청 수`를 표시한다. null을 실제 0으로 계산하지 않는다.
- 월 비용은 대상 서비스·경로의 모든 요청에 토큰이 있고 단가·가정값을 모두 입력해야 계산한다. 기본 대상은 `--service`의 `/rag-query`이고, 접두사가 있는 다중 서비스 로그는 `--forecast-service`로 정확한 그룹 이름을 지정한다.
- 토큰 미측정분·STT/TTS 요금은 포함하지 않는다. Java의 일반 텍스트 로그는 이 공통 JSON 통계 대상이 아니다. 503 세부 원인·사용자 안내·재시도 UX는 별도 시연으로 확인한다.
- 민감정보 의심 행은 통계에서 제외하고 종류·건수·일부 행 번호만 출력한다. 패턴 미탐지가 원문·개인정보 부재를 보증하지 않으므로 표본 점검을 병행한다.
- 종료 코드 0은 집계 완료, 1은 민감정보 의심·JSON/요청/토큰 형식 오류·집계 대상 없음, 2는 인자·입력 읽기 오류다. 0이어도 단가 미설정이면 비용은 미산정일 수 있다.

### 9. 확인한 범위와 남은 통합 작업

2026-10-24까지 남긴 검증 기록 기준이다. 아래 결과는 매 실행의 자동 보증이나 전체 서비스 완료 선언이 아니다.

**확인한 범위**

- Java API 11개 구현 및 개별 API 검증. 사용자 테스트에서 헬스 200/DB 중지 503, 가입·로그인·프로필·팀 API를 확인했다.
- Vue와 실제 Java 서버의 회원가입·로그인·프로필 변경·팀 참여·로그아웃을 화면에서 확인했다. 인증·CORS 보완 API 점검도 수행했다.
- common-py 자동 테스트 125개 통과. Java가 실제 발급한 JWT를 Python 공통 검증 함수로 확인했다.
- auth-server Docker 빌드·별도 18080 실행에서 35항목 통과. 기존 DB에 `ddl-auto=validate`로 연결했고 DB 스키마·데이터 유지도 대조했다. 해당 컨테이너 검증은 macOS arm64 환경이다.
- E2E 스크립트의 Bash 구문, ops_report의 Python 3.11 구문을 확인했다. ops_report 계산은 가상 로그로 점검했으며 실제 운영 측정치가 아니다.

**남은 작업**

- 별도의 새 DB에 001·002·900을 실제 적용해 JPA 매핑·기동, 2팀·5계정 생성, 각 계정의 로그인·역할·소속과 미가입 상태를 확인. 시드 구성 보완은 완료했으며 실제 DB 적용은 아직 하지 않았다.
- RAG·데이터·음성 담당자가 common-py를 자신의 앱·오류·권한·로그에 적용하고 실제 저장소와 연결.
- 실제 PDF·두 팀 계정으로 `scripts/e2e_check.sh` 실행. 현재 필수 1~5단계의 실제 RAG 통합 PASS 기록은 없다.
- 실제 서비스 로그로 `scripts/ops_report.py` 실행하여 지연·토큰·비용·로그 점검 결과 확보. 현재 실제 로그 실행은 하지 않았다.
- 배포 담당과 전체 Compose·서비스명 통신·헬스체크·DB/FAISS/모델 캐시 영속성 확인. 전체 Compose 성공 기록은 아직 없다.
- 선택 음성 STT→RAG→TTS, 전체 평가셋·개선 전후·운영 수치·발표 자료는 각 담당 결과와 함께 최종 점검.

이 파일은 백엔드 README 기여분이다. 루트 README에 취합할 때 전체 서비스 실행 순서·실제 주소·데이터/평가 결과를 각 담당 문서와 맞춘다.
