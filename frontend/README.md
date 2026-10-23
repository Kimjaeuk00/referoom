# 레퍼룸 프론트엔드

Vue 3 + Vite 웹 앱. 화면 요구사항은 DEV_02, API 계약은 DEV_01(인증)·DEV_03(라이브러리)·DEV_04(질의·음성)를 따른다. 백엔드 코드는 이 폴더에 없다.

## 실행

```bash
npm install
cp .env.example .env   # 처음 한 번
npm run dev            # http://localhost:5174 (백엔드 CORS 허용 Origin과 같은 포트)
```

`.env`

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VITE_AUTH_URL` | `http://localhost:8080` | 인증서버 |
| `VITE_RAG_URL` | `http://localhost:8001` | RAG·데이터 서비스 |
| `VITE_VOICE_URL` | `http://localhost:8008` | 음성 서비스 |
| `VITE_USE_MOCK` | `true` | `true`면 서버 없이 `src/api/mock`의 응답으로 동작. 실제 API가 준비되면 `false` |

## 목업 모드에서 시험하기

시연 흐름(DEV_05 5.1)과 같게 맞춰 두었다. LoRA·QLoRA는 처음부터 라이브러리에 있다.

- 계정(비밀번호는 아무 값): `minsu`(개발팀 팀원, L1), `admin`(개발팀 관리자, L3), `rnd`(R&D팀 관리자, 빈 라이브러리), `noteam`(팀 없음), `fail`(로그인 실패)
- 초대 코드: `K3F9Q2XA`(플랫폼개발팀), `R7M2PQ4C`(선행연구팀)
- `admin`으로 라이브러리의 **지금 동기화** → DoRA가 들어오고, 첨부 없는 논문 하나는 실패로 남는다
- **주제로 찾기**에서 `VeRA` → 후보를 골라 수집. 관리자는 끝난 뒤 **이번 수집 되돌리기**로 롤백할 수 있다
- 질문으로 시나리오 고르기: 기본 → LoRA 답변(출처 2개) / "어텐션"·"수식" → 원문 확인 권장 / "DoRA"·"VeRA"(라이브러리에 없을 때)·"없는" → handoff / "503"·"타임아웃"·"401" → 에러 / "느린" → 12초 지연 / "xss" → sanitize 확인
- PDF 파일 이름에 `dup`이 있으면 409, `scan`이 있으면 배치에서 "텍스트 추출 불가"로 실패
- 주제 검색어가 `zzz`면 후보 0건
- 새로고침하면 목업 데이터가 처음으로 돌아간다

## 음성 기능

녹음·재생 composable(`src/composables/useRecorder.js`, `useAudioPlayer.js`)은 음성 담당 파일이다. 두 파일이 있으면 상단 **음성 튜터** 메뉴와 Q&A의 **말로 묻기**·**답변 듣기** 버튼이 켜지고, 없으면 숨겨진다. 기대하는 반환 모양은 `src/lib/voice.js` 맨 위에 적어 두었다.

## 확인

```bash
npm test        # 토큰 디코딩·에러 매핑 검사
npm run build
```

## 배포

```bash
docker build -t referoom-web .
```

compose에서는 `web: { build: ./frontend, ports: ["5174:80"] }`. `VITE_*`는 브라우저가 접근하는 주소라서 빌드 인자(`--build-arg VITE_RAG_URL=...`)로 넘긴다. nginx가 모든 경로에 `index.html`을 돌려줘서 새로고침해도 화면 주소가 유지된다.
