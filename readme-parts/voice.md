# 음성 담당 전달 사항

Python 3.11의 uv 가상환경과 ffmpeg를 사용합니다. voice-service 디렉토리에서 실행합니다. 가상환경이 없으면 먼저 uv venv --python 3.11로 생성합니다.

```bash
uv pip install --python .venv/bin/python -r requirements.txt
uv run --no-project --python .venv/bin/python python -m uvicorn app.main:app --host 127.0.0.1 --port 8008
```

변수 예시는 voice-service/.env.example에 있으며 실제 값은 .env에 설정합니다. OPENAI_API_KEY, JWT_SECRET, CORS_ALLOWED_ORIGINS, WHISPER_MODEL, TTS_MODEL/TTS_VOICE, EVAL_JUDGE_MODEL 및 판정 연결/읽기 제한을 사용합니다. 실제 .env는 커밋하지 않습니다. 기본 Whisper는 small/CPU int8, TTS는 tts-1/nova입니다.

현재 /health는 모델 준비 시 200, 준비 전 503입니다. /docs·/redoc에는 등록된 /health만 표시됩니다. 공통 인증·Docker·기본 E2E는 대기/보류이며 /stt·/tts·/audio는 실제 앱 미등록으로 404입니다. /voice-qa와 RAG 클라이언트·낭독문 처리는 미구현입니다. 기존 HTML은 새 API 시연 화면이 아닙니다.

라우터의 계약은 /stt multipart audio/language → text/language/duration_s/latency_ms, /tts JSON text/voice → audio_id/audio_url/latency_ms, /audio/{id} 소유자 MP3 다운로드입니다. 입력은 10MB/60초, 생성 음성은 UUID로 저장하고 10분 만료·주기 정리를 적용합니다. 실제 JWT 인증·공통 오류·로그·고정 키 제거·운영 Docker·최종 통합 검증은 미완료입니다.

독립 P0 점검에서 비활성 레거시의 원문·경로·예외 상세 로그를 제거했고 uploads 잔존 파일이 없음을 확인했습니다. torch 직접 의존성은 현재 추론 경로에서 불필요함을 확인해 requirements에서 제외했습니다. torch 임포트 차단 상태의 테스트와 실제 캐시 small 모델 워밍업도 확인했으며 기존 .venv 패키지는 삭제하지 않았습니다. 고정 키·중복 인증 제거와 공통 로그 연결은 여전히 미완료입니다.

프론트 전달 파일은 `frontend/src/composables/useRecorder.js`, `useAudioPlayer.js`입니다. 화면·공통 API·package.json은 프론트 담당 소유입니다.

- `useRecorder()`: state/error/blob/mimeType ref, start/stop/dispose. start는 권한 및 시작 완료를 기다리고 stop은 최종 Blob을 반환합니다. 자동 종료도 blob ref로 결과를 전달합니다. WebM/Opus 우선·MP4 폴백, 최대 60초, scope 해제 시 마이크 반환을 제공합니다. 녹음 파일명은 MIME에 맞춰 .webm/.mp4로 전송합니다.
- `useAudioPlayer({ apiBlob, baseUrl })`: state/error ref, play(path)/stop/dispose. 프론트 공통 apiBlob이 Bearer·credentials:omit·401 처리를 맡습니다. Blob Object URL로 재생하고 정지·종료·오류·scope 해제 시 URL을 반환합니다. 진행 중 다운로드를 취소하는 대신 늦은 결과를 폐기합니다.

위 세부 호출 형식은 명세 공백에 대한 내부 구현 선택입니다. 공통 JWT/API 계약은 변경하지 않았습니다. 실제 Vue 렌더링·Chrome/Safari 녹음 및 인증 오디오 재생은 프론트 환경이 준비된 후 확인해야 합니다.

평가 도구는 eval/questions/*.jsonl을 합쳐 검증하고 RAG 응답·근거·거절·지연 및 선택 BM25를 수집합니다. 실제 고정 PDF·평가 문항이 없어 최종 정확성/환각·전후 개선 수치·배포 판단은 미완료입니다. 팀원 소유 rag.jsonl과 루트 배포 파일은 수정하지 않습니다.

```bash
# voice-service에서 도움말 확인
uv run --no-project --python .venv/bin/python python ../eval/run_eval.py --help

# 실제 평가셋·RAG·TOKEN·EVAL_TIMEOUT_SECONDS 준비 후 수집
uv run --no-project --python .venv/bin/python python ../eval/run_eval.py \
  --base-url http://localhost:8001 --token "$TOKEN" \
  --timeout "$EVAL_TIMEOUT_SECONDS" --tag baseline
```

결과는 eval/results/{날짜}_{태그}.csv 및 .md입니다. BM25는 기존 text/metadata(team_id,source,page) 청크를 --corpus/--team-id로 읽으며 현재 동일 PDF 전체 범위만 비교합니다. 실제 RAG 검색 Recall@k 연결은 남아 있습니다. 최종 인용을 전체 검색 결과로 대체하지 않습니다.

루브릭 v1의 판정/집계·사람 점수·명시 단가 추정·오프라인 재집계에 사용자 지정 OpenAI gpt-6-luna 어댑터를 연결했습니다. 연결 5초/읽기 대기 30초도 사용자 확정이며 --judge-openai를 명시하면 유료 호출합니다. 합성 1건 연결 검증은 성공했지만 최종 평가/사람 판정 일치도는 대기입니다. 판정 설명은 voice-service/evaluation/rubric.json, 모델 연결은 evaluation/openai_judge.py, 판정 결과 검증·집계는 eval/run_eval.py에서 수정합니다. 규칙 변경 시 version을 올리고 전후를 같은 모델·루브릭·자료로 재평가합니다. 판정기 실패·불완전한 근거·누락 토큰을 통과/환각 없음/무료로 처리하지 않습니다.

STT 기술 용어 10문장 비교 도구는 `voice-service/scripts/benchmark_stt.py`입니다. 같은 녹음에서 initial_prompt 적용 전후를 측정하고, 간이 문자 오류율(CER)과 추론 지연을 기록합니다. 실제 녹음·정답이 아직 없어 품질 측정은 대기입니다. 입력과 기본 결과는 Git 제외인 voice-service/data/stt-benchmark/ 아래에 두며, 원문을 결과에 저장하지 않습니다. CER은 내부 간이 측정 방법이며 요구서가 지정한 공식 합격 지표가 아닙니다. 모델 변경·다운로드는 이번 구현에서 실행하지 않았습니다.

로컬 독립 검증은 Python 141개·JavaScript 20개가 통과했습니다. 테스트와 개인 기획/관리 문서는 사용자 선택으로 이번 업로드에서 제외하며 로컬에 유지합니다. 이 검증은 실제 인증·음성 품질·Vue·팀 서비스 통합을 대신하지 않습니다. 현재 Dockerfile은 개발용으로 루트 build context·common-py 설치·--reload 정리가 필요합니다. 최종 평가·사람 검토·전후 CHANGELOG도 남아 있으므로 배포 완료본이 아닙니다.
