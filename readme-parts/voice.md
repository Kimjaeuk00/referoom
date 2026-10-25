# 담당 B 인계: 음성 서비스·개발 실행 환경

기준: 2026-10-25, v0.2 분업계획 및 현재 로컬 구현. 아래 명령은 모두 **저장소 루트**에서 실행한다. 구현·검증 완료와 실제 통합 미확인 항목을 구분한다. Git 업로드·병합 완료를 뜻하지 않는다.

## 1. 담당 범위와 현재 상태

B는 음성 서버, `scripts/dev.sh`·`scripts/dev/**`, 지정 Dockerfile, `.gitignore`, 본 문서를 담당한다. 루트 `.dockerignore`는 사용자 승인으로 추가했다.

**프론트 전체(음성 composable·화면 포함), `eval/**`, RAG 앱·테스트·requirements, `scripts/e2e_check.sh`·`ops_report.py`는 A 소유다.** B는 해당 소스를 직접 수정하지 않고 테스트를 실행하거나 변경을 요청한다. `common-py` 변경은 별도 공통 PR 규칙을 따른다.

| 작업 | 현재 상태 | 남은 확인 |
|---|---|---|
| B0 실행 기반 | 구현·검증 완료 | Git 작업 별도 |
| B3 실행 관리 | 최종 감사에서 수정 필요 2건 | 정지 DB 포트 판별·테스트 포트 격리 보완, DB·5서비스 기동 보류 |
| B1 공통 인증 | 구현·가짜 STT/TTS 검증 완료 | 실제 Java 발급 토큰 연결 |
| B2 음성 튜터 | 백엔드·가짜 RAG HTTP·폴백 검증 완료 | A의 수동 재시도 UI·실제 RAG/TTS·화면 연결 |
| B4 Docker | 세 이미지 빌드·Compose 설정 검증 완료 | 컨테이너 실제 기동·통신·배포는 이번 범위 밖 |
| B5 인계 | 본 문서 최신화 | 작업 변경 시 함께 갱신 |

## 2. 환경과 실행 방법

Python 3.11·uv·ffmpeg를 사용한다. 개발 스크립트는 Bash 3.2를 지원한다. 프론트에는 Node/npm, 인증서버에는 Java 21·Gradle Wrapper가 필요하다. DB는 기존 `referoom-mariadb` 컨테이너를 사용하며 스크립트가 새 DB를 만들거나 초기화하지 않는다.

```bash
./scripts/dev.sh --help
./scripts/dev.sh setup
./scripts/dev.sh init-env
./scripts/dev.sh up voice
```

- `setup`: RAG·음성의 Python 3.11 `.venv`, 기존 의존성·공통 패키지·개발 의존성 설치, 프론트 설치, Gradle 확인. uv가 없을 때는 Python 3.11 venv+pip 대체 경로가 있다. 입력 목록과 의존성을 확인해 반복 설치를 건너뛴다. 프론트 lockfile이 있으면 `npm ci`를 사용해 보존한다.
- `init-env`: 루트 `.env`에 `JWT_SECRET`이 없을 때만 생성·추가한다. 값은 출력하지 않으며 기존·빈 키를 임의 교체하지 않는다. 키가 있으면 Java·RAG·음성이 같은 값을 사용하는지 확인한다.
- `up [서비스...]`: `db auth rag voice frontend` 선택 가능. 인자 없으면 DB→인증→RAG→음성→프론트 순으로 실행한다. **전체 기동은 현재 DB 검증 보류 상태**다.
- `down [서비스...]`: 이 스크립트가 관리하는 프로세스만 종료한다. PID·시작 정보·프로세스 그룹 확인, 종료·포트 반환 대기를 수행한다. 외부에서 이미 실행 중이던 DB는 종료하지 않는다.
- `status`: 프로세스·헬스 상태 요약. `logs <서비스>`: 로그 확인(Ctrl+C로 종료). `restart <서비스>`: 관리 서비스 재시작.
- `test`: 공통·RAG·음성·프론트 테스트 및 인증 빌드를 실행해 요약한다. Python 테스트의 외부 네트워크를 차단한다. 실제 유료 테스트는 별도다.

실행 기록은 `.run/pids/`, `.run/logs/`에 두며 Git에서 제외한다. 사용 중인 포트를 강제로 비우지 않는다. 일부 시작에 실패해도 앞서 시작한 서비스는 유지되므로 `status`·`down`으로 확인한다. 실제 `.env`를 자동 덮어쓰지 않는다.

기본 포트: 인증 8080, RAG 8001, 음성 8008, 프론트 5174, DB 53301.

## 3. 환경변수

실제 비밀값은 로컬 `.env` 또는 실행 환경에만 둔다. [음성 환경 예시](../voice-service/.env.example)에는 변수명·기본 설정만 기록한다.

| 변수 | 용도·기본값 |
|---|---|
| `JWT_SECRET` | 필수. Java·RAG·음성이 동일한 문자열 사용. 누락·공백이면 음성 앱 기동 실패 |
| `CORS_ALLOWED_ORIGINS` | 기본 `http://localhost:5174,http://localhost:8008`. 쉼표 목록, `*` 금지 |
| `OPENAI_API_KEY` | 실제 TTS 합성 키. 로컬 STT에는 필요 없음 |
| `WHISPER_MODEL` | 기본 `small`, 현재 CPU/int8 |
| `TTS_MODEL` / `TTS_VOICE` | 기본 `tts-1` / `nova`. 실제 제공 여부·계정 접근은 별도 검증 |
| `RAG_URL` | 로컬 기본 `http://localhost:8001`. 기존 실제 `.env`가 설정돼 있으면 그 값이 적용됨 |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | 인증서버 실행용. 기본 localhost/53301/sql_db/root. 비밀번호는 직접 설정해야 함 |
| `FRONTEND_URL` | 인증서버용, 기본 `http://localhost:5174` |

개발 스크립트의 공유 설정 우선순위는 프로세스 환경→루트 `.env`→인증 `.env`→기본값이다. 서비스 전용 값은 프로세스 환경→서비스 `.env`→루트 `.env` 순이다. 직접 음성 앱 실행 시에는 서비스 `.env`, 과거 `app/.env`를 읽고 기존 프로세스 값을 덮어쓰지 않는다. 직접 실행에는 공유 키 주입을 별도로 준비한다.

평가용 `EVAL_JUDGE_MODEL=gpt-6-luna`, `EVAL_JUDGE_CONNECT_TIMEOUT=5`, `EVAL_JUDGE_READ_TIMEOUT=30`은 기존 평가 어댑터 설정이다. 음성 튜터의 RAG 모델을 지정하지 않으며 음성 API가 평가기를 자동 호출하지 않는다. `eval/**`의 모드별 개편·실행은 A 담당이다. 기존 STT 측정 도구는 남아 있지만 실제 품질 측정·튜닝은 이번 B 구현 완료에 포함하지 않는다.

## 4. API 계약

프론트는 `Authorization: Bearer <accessToken>`과 인증 fetch→Blob 재생을 사용한다. `common-py.require_team`으로 로그인·팀 가입을 확인한다. 공통 인증의 기존 쿠키 호환은 공유 모듈 규칙을 따르지만 `/voice-qa`는 RAG에 전달할 Bearer 헤더가 반드시 필요하다.

| API | 입력 | 출력·규칙 |
|---|---|---|
| `GET /health` | 인증 없음 | Whisper 준비 완료 200, 준비 전·실패 503 `NOT_READY` |
| `POST /stt` | multipart `audio`, 선택 `language=ko/en/auto` | `text`, `language`, `duration_s`, 숫자 `latency_ms` |
| `POST /tts` | JSON `text`, 선택 `voice` | `audio_id`, `audio_url`, 숫자 `latency_ms` |
| `GET /audio/{audio_id}` | 인증 헤더 | 요청자 소유·만료 전 MP3. 타인·만료·누락은 동일한 404 |
| `POST /voice-qa` | 아래 multipart | 인식문·답변·출처·낭독문·선택 음성·단계별 지연 |

오디오 입력은 10MB·60초 제한이다. 원본·정규화 임시 파일은 STT 처리 후 정리하고 인식문·답변을 로그·별도 파일에 저장하지 않는다. 생성 음성은 `data/audio/{user_id}/`에 UUID·소유자·만료 정보로 보관하며 10분 만료, 시작 시·주기적으로 정리한다. 공개 `/uploads`·레거시 시험 페이지·번역 API는 제공하지 않는다. Swagger는 `/docs`다.

공통 오류는 `{detail, code}`다. 무인증/잘못된 토큰 401, 만료 `TOKEN_EXPIRED`, 팀 미가입 403 `NO_TEAM`, 입력 오류 422 `VALIDATION_ERROR`, 빈 인식 422 `STT_EMPTY`. `X-Request-Id`를 응답·CORS에 노출하고 요청 ID·상태·지연·사용자/팀 식별자를 기록한다. 원문·JWT는 액세스 로그에 넣지 않는다. 모든 미처리 500의 CORS까지 검증한 것은 아니다.

### `/voice-qa` 요청

| 필드 | 계약 |
|---|---|
| `audio` | 필수 파일 |
| `view` | 선택 dev/rnd. 생략 시 검증된 사용자 view |
| `source` | 선택 pdf/web/all, 기본 all |
| `scope` | 선택 JSON 문자열. all/paper/tag 범위, 생략 시 all |
| `speak` | 문자열 true/false, 기본 true. false이면 TTS 생략 |
| `language` | 선택 ko/en/auto, 기본 ko |
| `level` | 선택 L1/L2/L3 호환값. 질문 1회 표현 조정이며 사용자 설정·JWT에 저장하지 않음 |

음성 튜터는 기본 튜터 `/rag-query`를 호출한다. 사용자 Authorization 헤더·안전한 요청 ID를 그대로 전달하고 `team_id`를 별도 지정하지 않는다. 팀 격리는 RAG가 토큰으로 수행한다. 연결 5초·읽기 30초, 자동 재시도·리다이렉트 없음. 총 처리 시간 상한과는 다르다.

### `/voice-qa` 응답 예시

아래 값은 계약 예시이며 측정값이나 실제 논문 답변이 아니다. 음성을 생략한 예시다.

```json
{
  "stt_text": "인식한 질문",
  "answer": "답변 예시 [S1]",
  "sources": ["논문 예시 p.1"],
  "source_details": [{"label": "S1", "title": "논문 예시", "page": 1, "snippet": "근거 예시"}],
  "needs_review": false,
  "handoff": false,
  "level": "L2",
  "view": "rnd",
  "speech_text": "답변 예시. 자세한 내용은 화면을 확인하세요.",
  "audio_id": null,
  "audio_url": null,
  "latency_ms": {"stt": 0, "rag": 0, "tts": 0, "total": 0}
}
```

RAG 응답의 `level`은 호환 유지한다. 사용자 DB·JWT의 level은 복원하지 않는다. RAG 단독 `latency_ms`는 숫자지만 음성 튜터는 `{stt,rag,tts,total}` 객체다. 낭독문은 라벨·Markdown·URL을 정리하고 수식을 화면 참조로 대체하며 안내 포함 600자 이내다. 근거 없음은 고정 handoff 문구를 읽는다. 낭독문 생성에 추가 LLM을 호출하지 않는다.

RAG 오류의 HTTP 상태·알려진 코드는 유지하고 상세 메시지는 일반 안내로 바꾼다. 시간 초과 503 `UPSTREAM_TIMEOUT`, 연결 불가 503 `NOT_READY`. 잘못된 성공 응답·리다이렉트는 내부 매핑 502 `UPSTREAM_ERROR`다.

### 폴백과 A 연결 사항

TTS·음성 저장 실패에도 **답변·출처·낭독문을 반환**하고 `audio_id/audio_url`은 null이다. 자동 유료 재시도는 없다. `speak=false`도 null이므로 요청의 speak와 함께 해석한다. TTS 실패를 RAG의 근거 없음(handoff)으로 바꾸지 않는다.

사용자가 다시 듣기를 선택하면 반환된 `speech_text`로 기존 `/tts`만 1회 재시도하고 STT·RAG는 재실행하지 않는 정책이다. **버튼·실패 안내·질문별 1회 제한은 A 프론트 연결 대기**이며 현재 범용 `/tts`가 서버에서 횟수를 강제하지는 않는다. 재시도도 실패하면 답변·출처를 유지하고 추가 유료 재시도를 중단해야 한다.

A 전달: `frontend/src/views/VoiceTutorView.vue`에서 speak=true인데 audio_url이 없으면 음성 실패 안내와 수동 1회 재시도를 연결한다. 기존 `speech_text`로 `/tts`→응답 음성 Blob 재생, 기존 턴의 답변·출처는 유지한다. B는 해당 파일을 수정하지 않았다. 모든 모드 마이크는 `/stt` 텍스트 입력 수단이며 듣기·음성 튜터는 튜터 모드에 한정하는 화면 규칙도 A 확인 대상이다.

## 5. Docker 빌드

```bash
docker build -t referoom-voice:b4 -f voice-service/Dockerfile .
docker build -t referoom-rag:b4 -f rag-service/Dockerfile .
docker build -t referoom-auth:b4 -f auth-server/Dockerfile .
docker compose -f voice-service/docker-compose.yml config --quiet --no-interpolate
```

세 Dockerfile 모두 루트 context다. Python 이미지는 uv 가상환경·공통 패키지 일반 설치·비루트 app 사용자·reload 없는 실행을 사용한다. RAG는 공식 CPU PyTorch를 선택해 ARM NVIDIA 의존성 오류를 해결했다. RAG requirements·모델 이름·소스는 바꾸지 않았다. 모델은 빌드 중 다운로드하지 않는다.

실제 .env는 이미지에서 제외하고 기동 시 환경변수로 주입한다. 두 Python 이미지의 모델 캐시는 `/home/app/.cache/huggingface`다. 실행 시 해당 경로를 캐시 볼륨으로 사용한다. 음성 단독 Compose는 이 캐시와 `/app/voice-service/data` 볼륨을 정의한다. 호스트 RAG 주소 기본값은 `http://host.docker.internal:8001`이고 실제 통신은 미검증이다. 전체 루트 Compose·컨테이너 통합·배포는 이번 B4 범위 밖이다.

## 6. 유료 호출 없는 테스트와 확인 결과

```bash
uv run --no-project --python voice-service/.venv/bin/python python -m pytest -q voice-service/tests
uv run --no-project --python voice-service/.venv/bin/python python -m unittest discover -s scripts/dev/tests -v
./scripts/dev.sh test
```

음성 테스트는 가짜 키·STT/TTS·MockTransport·임시 음성 저장소·네트워크 차단을 사용한다. 키·실제 녹음 없이 실행할 수 있다. DB 전체 기동은 test 명령의 대상이 아니다. 인증 빌드는 실제 로그인 성공을 뜻하지 않는다.

| 검증 기록 | 결과 | 범위 |
|---|---|---|
| 음성 전체 pytest | 96 passed | 인증·API·RAG 전달·폴백·낭독문·소유권/만료 |
| B3 실행 관리 unittest | 최신 감사 14 passed / 1 ERROR | 실제 8008 포트 의존 테스트 보완 필요. 이전 15 passed는 당시 환경 결과 |
| 공통 / RAG / 프론트 | 129 passed / 193 passed, 2 skipped / 27 passed | 기존 담당 테스트 실행만 |
| 인증 빌드·전체 test | 성공 / 종료 0 | 실제 DB·Java 로그인과 구분 |
| 프론트 수명주기 | 2회 통과 | 실행·중복 방지·HTTP 200·재시작·종료 |
| 로컬 HTTP 음성 튜터 | 통과 | 가짜 RAG/TTS, 폴백 뒤 TTS만 수동 재시도·파일 다운로드 |
| Docker | 세 이미지·Compose·ignore 검사 통과 | Docker 29.6.1, linux-arm64. 서비스 기동 없음 |

첫 기동은 Whisper 준비가 필요하다. 이미 음성 서버를 실행한 상태에서 아래 요청은 유료 합성을 수행하지 않는다.

```bash
curl -i http://127.0.0.1:8008/health
curl -i -X POST http://127.0.0.1:8008/tts -H 'Content-Type: application/json' -d '{"text":"테스트"}'
```

health는 준비 중 503·준비 완료 200, 무토큰 TTS는 401 `UNAUTHORIZED`가 정상이다. 실제 서버 기동·모델 준비를 이번 문서 작업에서 재실행한 것은 아니다.

## 7. 미완료·보류 및 비용 승인

- DB·실제 Java 로그인·5서비스 전체 기동: 사용자 요청으로 보류.
- 실제 마이크 녹음 STT 품질·지연, 실제 RAG·API 잔량/최종 청구, 브라우저 녹음·재생·전체 화면 E2E: 미검증. TTS 1회·합성음성 STT의 후속 검증은 아래 기록 참조.
- 수동 듣기 1회 UI·실패 표시·횟수 제한: A 연결 필요. 다른 팀 코드 직접 수정 금지.
- Docker 서비스 기동·볼륨 지속성·컨테이너 간 통신·GPU/다른 아키텍처·배포: 현재 검증 범위 밖.
- 기존 STT 측정 도구는 코드가 있으나 실제 녹음·정답 기반 측정은 미완료. 모드별 eval 개편·최종 품질/비용 평가 및 E2E 스크립트 유지보수는 A 담당.

실제 외부 API 테스트는 **모델·건수·토큰/문자수·재시도·예상 비용·중단 기준을 먼저 보고하고 해당 묶음 승인을 받은 후 실행**한다. 키 설정은 유료 실행 승인이 아니다. `/voice-qa`는 speak=false라도 RAG LLM 비용이 발생할 수 있다. 승인 없는 자동 유료 재시도·모델 교체·전체 평가 실행을 하지 않는다. 실패·시간 초과에 사용량이 불명확하면 무료로 간주하지 않는다.

추가 실행·API 세부사항은 [음성 README](../voice-service/readme.md), 환경변수 이름은 [환경 예시](../voice-service/.env.example)를 참고한다. 개인 진행 문서를 팀 실행의 필수 전제로 삼지 않는다.

## 실제 음성 단독 테스트 기록 (2026-10-25)

tts-1/nova 25자 1회: HTTP 200, MP3 52608바이트·3.288초, 추정 $0.000375. 로컬 STT HTTP 200, 3039ms, 브랜드명 레퍼룸→래퍼룸으로 정확 일치 아님.

사용자가 승인한 최대 100자·1회 범위에서 25자만 합성했고 자동 재시도·RAG 호출은 없었다. 공식 문자 단가로 추정한 비용이며 최종 청구 내역은 조회하지 않았다. 생성 MP3를 WAV로 바꿔 로컬 Whisper에 보낸 STT는 추가 유료 호출이 아니다. 실제 마이크 입력이나 기술 용어 10문장 품질 검증을 대신하지 않는다.

DB 없이 음성 서버만 기동하고 1시간 유효한 로컬 진단 JWT로 확인했다. Java 로그인 토큰·실제 팀 연결 검증은 아니다. 진단 토큰은 비밀키와 함께 출력하지 않고 Git 제외 .run의 비공개 파일에 보관했다. OpenAI 키는 voice-service/.env에서 사용하며 브라우저에는 전달하지 않는다.

브라우저 확인: 음성 서버가 실행 중이면 http://127.0.0.1:8008/docs 에 접속한다. Authorize에는 로컬 진단 JWT 또는 정상 발급한 사용자 JWT 문자열을 입력한다. POST /stt에서 지원 녹음 파일을 선택하면 실제 로컬 인식을 확인할 수 있다. 실제 TTS 1회 승인은 이미 사용했으며 추가 /tts·/voice-qa 유료 호출은 별도 비용 보고·승인 후 수행한다. 진단 파일은 세션 로컬 산출물이므로 팀 실행 필수 파일이 아니다. 토큰은 1시간, 서버 생성 음성은 10분 후 만료된다.

### 사용자 실제 마이크 확인 (2026-10-25)

사용자가 기존 웹 화면의 실제 마이크 STT 동작을 확인했다. 로컬 진단 세션에서의 기능 확인이며 Java 로그인·실제 RAG 통합·정량 정확도/지연 검증과 구분한다. 최종 감사에서 B3 수정 필요 2건이 확인돼 통합 준비 판정은 보류한다. 병합 후 실제 로그인→논문 질의→답변/출처→음성 재생·팀 격리를 검증하고 A의 수동 1회 재시도 UI를 연결해야 한다. 단순 Git 병합을 전체 기능 완료로 판단하지 않는다.
