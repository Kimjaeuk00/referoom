# 음성 서비스

Python 3.11·uv·ffmpeg를 사용합니다. 저장소 루트에서 실행합니다.

```bash
./scripts/dev.sh setup
./scripts/dev.sh init-env
./scripts/dev.sh up voice
```

init-env는 없는 경우에만 루트 .env에 공통 JWT_SECRET을 추가합니다. 기존 값을 덮어쓰거나 화면에 출력하지 않습니다. 실행 스크립트는 같은 키를 서버에 주입합니다. 직접 uvicorn으로 실행할 때도 Java·RAG와 같은 JWT_SECRET을 환경에 주입해야 합니다. 실제 .env는 커밋하지 않습니다.

- 상태: `http://localhost:8008/health` — Whisper 준비 완료 200, 준비 중·실패 503. 인증 없이 확인합니다.
- API 문서: `http://localhost:8008/docs` — STT·TTS·음성 다운로드의 Bearer 인증 계약을 확인합니다.
- STT: `POST /stt`, multipart audio/language. 10MB·60초 제한, ko/en/auto.
- TTS: `POST /tts`, JSON text/voice. 기본 nova, 요청자 소유 음성 저장.
- 다운로드: `GET /audio/{audio_id}`, 동일 사용자만 접근, 10분 만료. Bearer fetch→Blob 방식으로 사용합니다.
- 공통 인증·팀 권한·오류·요청 ID·로그는 common-py를 사용합니다. 사용자 level claim은 요구하지 않습니다.
- 사용하지 않는 자체 JWT 라우터는 정리했고, 과거 HTML·uploads 경로는 제공하지 않습니다. 기존 HTML 파일은 참고용으로 보존했습니다.
- 음성 튜터: `POST /voice-qa`, multipart audio/view/source/scope(JSON 문자열)/speak. language·질문 1회용 level도 선택 입력입니다. STT→기본 튜터 RAG→선택 TTS 순서로 처리합니다.
- RAG 응답의 답변·출처·level 호환 필드를 유지하고 stt_text, speech_text, audio_id/audio_url, latency_ms 객체(stt/rag/tts/total)를 반환합니다.
- TTS 실패에도 답변·출처를 반환하며 audio_id/audio_url은 null입니다. speak=false도 음성을 생성하지 않고 null을 반환합니다. 자동 유료 재시도는 없습니다.
- 수동 듣기 재시도는 반환된 speech_text로 기존 /tts만 호출하는 방식입니다. 한 번만 허용하는 UI·실패 안내는 A의 프론트 연결 대기입니다. /tts 자체는 범용 API이며 서버가 질문별 재시도 횟수를 강제하지는 않습니다.
- RAG 연결 5초·읽기 30초, 요청 1회·리다이렉트 미추적. 실제 RAG_URL은 .env 또는 프로세스 환경으로 지정합니다. 로컬 기본은 http://localhost:8001이며 .env.example을 고쳤어도 기존 실제 .env는 자동으로 바뀌지 않습니다.

첫 기동은 Whisper 모델 준비 시간이 필요합니다. 가짜 응답 검증과 실제 호출은 구분하며, 후속 실테스트 기록은 아래를 참고합니다. 실제 TTS 및 외부 LLM 테스트는 비용 보고·사용자 승인 후 실행합니다.

## 유료 호출 없는 검증

```bash
uv run --no-project --python voice-service/.venv/bin/python python -m pytest -q voice-service/tests
./scripts/dev.sh test
```

음성 테스트는 실제 API 키 대신 가짜 키, 가짜 STT/TTS, 임시 음성 저장소 및 네트워크 차단을 사용합니다. B2 포함 현재 음성 테스트는 96개 통과입니다. RAG는 httpx.MockTransport로 대체합니다. 전체 실행 도구는 Python 테스트의 외부 네트워크도 차단합니다. DB·실제 Java 로그인·음성 품질·최종 화면 E2E는 별도 검증 대상입니다.

```bash
curl -i http://127.0.0.1:8008/health
curl -i -X POST http://127.0.0.1:8008/tts \
  -H 'Content-Type: application/json' -d '{"text":"테스트"}'
./scripts/dev.sh down voice
```

두 번째 요청은 토큰이 없으므로 401 UNAUTHORIZED가 정상이며 실제 합성을 호출하지 않습니다. 모델 준비 중에도 보호 API가 인증을 우회하지 않아야 합니다. API 문서에서 토큰을 넣고 실제 /tts를 실행하면 비용이 발생할 수 있으므로 유료 테스트 승인 후 진행합니다.

상세 계획·진행·문제는 B_IMPLEMENTATION_PLAN.md를 참고합니다. Git 작업은 별도 사용자 지시 후 진행합니다.

## B2 응답·검증 범위

```json
{
  "stt_text": "인식한 질문",
  "answer": "근거 답변 [S1]",
  "sources": ["논문 p.1"],
  "source_details": [],
  "needs_review": false,
  "handoff": false,
  "level": "L2",
  "view": "rnd",
  "speech_text": "낭독문. 자세한 내용은 화면을 확인하세요.",
  "audio_id": null,
  "audio_url": null,
  "latency_ms": {"stt": 0, "rag": 0, "tts": 0, "total": 0}
}
```

위 값은 형식 예시이며 실측 결과가 아닙니다. null 음성은 speak=false 또는 합성 실패일 수 있으므로 요청의 speak와 함께 해석합니다. TTS 실패를 근거 없음(handoff)으로 바꾸지 않습니다. 낭독문은 라벨·Markdown·URL을 정리하고 수식은 화면 참조로 대체하며, 안내 포함 최대 600자입니다. handoff는 고정 문구를 사용합니다.

RAG 오류는 HTTP 상태와 알려진 코드가 유지되지만 상세 메시지는 원문·제공자 정보 노출을 막기 위해 일반 안내로 대체합니다. 연결·읽기 제한 시간 초과는 503 UPSTREAM_TIMEOUT, 연결 불가는 503 NOT_READY입니다. 잘못된 성공 응답·리다이렉트는 내부 매핑으로 502 UPSTREAM_ERROR입니다.

현재 테스트는 실제 Java 로그인·마이크 녹음 품질·실제 RAG·브라우저 재생 품질은 미검증입니다. 실제 TTS 1회·합성음성 STT의 후속 결과는 아래와 같습니다. /voice-qa는 speak=false여도 RAG에서 유료 LLM을 호출할 수 있으므로 실제 호출 테스트는 사전 비용 보고·승인 후 진행합니다.

## B4 Docker 빌드 (서비스 기동은 별도)

모든 빌드는 저장소 루트를 기준으로 실행합니다. 실제 .env·가상환경·생성 음성·업로드·모델 캐시·문서는 루트 .dockerignore로 제외하고, common-py 설치에 필요한 README만 예외로 유지합니다. Python 서비스는 uv 0.12.13으로 /opt/venv를 만들고 공통 패키지를 일반 설치합니다. uv 도구 자체만 기본 Python pip로 설치합니다.

```bash
docker build -t referoom-voice:b4 -f voice-service/Dockerfile .
docker build -t referoom-rag:b4 -f rag-service/Dockerfile .
docker build -t referoom-auth:b4 -f auth-server/Dockerfile .
docker compose -f voice-service/docker-compose.yml config --quiet --no-interpolate
```

2026-10-25 Docker 29.6.1/linux-arm64에서 세 이미지 빌드와 Compose 설정 검증을 통과했습니다. Python 의존성 검사·주요 패키지 import·공통 패키지 비편집 설치·복사 영역 .env 부재는 빌드 단계에서 확인합니다. 세 이미지 모두 app 사용자로 실행하도록 설정했고 --reload와 실제 비밀 환경변수는 이미지에 포함하지 않았습니다.

RAG 최초 빌드에서는 기본 PyTorch의 NVIDIA 의존성 플랫폼 오류가 발생해 Dockerfile에서 --torch-backend=cpu를 사용했습니다. A의 requirements·RAG 소스·모델 이름은 변경하지 않았습니다. CPU PyTorch 2.14.1+cpu 설치 후 의존성 검사와 빌드가 통과했습니다. GPU 구성·다른 아키텍처는 검증하지 않았습니다.

모델은 빌드 중 다운로드하지 않습니다. 두 Python 이미지의 HF_HOME은 /home/app/.cache/huggingface이며, 실제 기동 시 이 경로를 캐시 볼륨으로 사용합니다. 음성 단독 Compose에는 whisper-cache와 voice-data(/app/voice-service/data) 볼륨을 정의했습니다. RAG 캐시도 해당 HF_HOME 경로에 별도 볼륨을 지정하는 방식이며 이번에는 컨테이너 기동·볼륨 영속성을 검증하지 않았습니다.

음성 단독 Compose는 context: .. 와 voice-service/Dockerfile을 사용합니다. 소스·가상환경 bind mount를 제거했고 실행 환경변수와 음성/모델 캐시 볼륨을 정의했습니다. 컨테이너에서 호스트 RAG를 호출할 때의 기본 RAG_URL은 http://host.docker.internal:8001이며 Linux 호스트 매핑도 설정했습니다. 실제 통신은 미검증입니다.

.env는 이미지에 넣지 않고 실행 시 --env-file 또는 프로세스 환경변수로 주입합니다. JWT_SECRET은 Java·RAG·음성이 같아야 합니다. 실제 키를 Dockerfile의 ARG/ENV나 빌드 명령에 적지 않습니다. Compose는 값이 없는 상태에서도 빌드·설정 검증이 가능하지만 실제 기동 시 JWT_SECRET이 없으면 앱이 실패합니다. 현재 .env를 자동 수정하거나 서비스 컨테이너를 기동하지 않았습니다.

전체 서비스를 묶는 루트 Compose·배포·DB·컨테이너 간 통신은 이번 B4 범위 밖입니다. Docker 빌드 다운로드는 수행했지만 외부 LLM/TTS 호출은 없었습니다.

참고: [Docker build context·ignore](https://docs.docker.com/build/concepts/context/), [uv PyTorch backend](https://docs.astral.sh/uv/guides/integration/pytorch/).

## 실제 음성 단독 테스트 기록 (2026-10-25)

tts-1/nova 25자 1회: HTTP 200, MP3 52608바이트·3.288초, 추정 $0.000375. 로컬 STT HTTP 200, 3039ms, 브랜드명 레퍼룸→래퍼룸으로 정확 일치 아님.

사용자가 승인한 최대 100자·1회 범위에서 25자만 합성했고 자동 재시도·RAG 호출은 없었다. 공식 문자 단가로 추정한 비용이며 최종 청구 내역은 조회하지 않았다. 생성 MP3를 WAV로 바꿔 로컬 Whisper에 보낸 STT는 추가 유료 호출이 아니다. 실제 마이크 입력이나 기술 용어 10문장 품질 검증을 대신하지 않는다.

DB 없이 음성 서버만 기동하고 1시간 유효한 로컬 진단 JWT로 확인했다. Java 로그인 토큰·실제 팀 연결 검증은 아니다. 진단 토큰은 비밀키와 함께 출력하지 않고 Git 제외 .run의 비공개 파일에 보관했다. OpenAI 키는 voice-service/.env에서 사용하며 브라우저에는 전달하지 않는다.

브라우저 확인: 음성 서버가 실행 중이면 http://127.0.0.1:8008/docs 에 접속한다. Authorize에는 로컬 진단 JWT 또는 정상 발급한 사용자 JWT 문자열을 입력한다. POST /stt에서 지원 녹음 파일을 선택하면 실제 로컬 인식을 확인할 수 있다. 실제 TTS 1회 승인은 이미 사용했으며 추가 /tts·/voice-qa 유료 호출은 별도 비용 보고·승인 후 수행한다. 진단 파일은 세션 로컬 산출물이므로 팀 실행 필수 파일이 아니다. 토큰은 1시간, 서버 생성 음성은 10분 후 만료된다.

## DB 보류 중 웹 마이크 확인

실제 API 모드의 프론트 localhost:5174에서 로컬 진단 JWT 세션으로 화면을 확인할 수 있다. 이는 Java 로그인 검증이 아니다. 진단 토큰은 1시간이며 세션 파일은 Git 제외 .run에만 둔다.

준비된 진단 Chrome 창에서 voice-local-diagnostic 이름을 확인한 뒤 홈의 초록 마이크→권한 허용→3~5초 발화→같은 버튼으로 종료하면 실제 /stt 인식문이 입력창에 들어온다. 로컬 STT는 추가 OpenAI 비용이 없다. 이 경로는 합성 WAV 스트림을 사용하는 임시 Chrome에서 MediaRecorder→STT 200→화면 반영까지 확인했다. 실제 사용자 마이크·다른 브라우저 품질은 별도다.

DB/인증/RAG가 없는 현재는 라이브러리·설정 조회 오류가 날 수 있고 질문 전송·답변 생성은 이번 확인 대상이 아니다. 실제 TTS 1회는 이미 승인·검증했으며 추가 합성 없이 기존 검증 MP3를 들어볼 수 있다. 추가 /tts·/voice-qa 호출은 별도 비용 승인이 필요하다. 프론트 소스 수정·가짜 응답 모드 전환은 하지 않았다.

### 사용자 실제 마이크 확인

2026-10-25 사용자가 기존 웹 화면에서 실제 마이크 음성 인식까지 동작함을 확인했다. 실제 입력 장치의 기능 확인은 완료했으나 정량 품질·지연 수치를 측정한 것은 아니다. 최종 감사에서 B3 수정 필요 2건이 확인돼 통합 준비 판정을 보류하며, A 병합 후 실제 Java 로그인·RAG·출처·재생·팀 격리·수동 1회 재시도 UI 확인이 남는다. DB 보류·유료 테스트 승인 규칙은 유지한다.
