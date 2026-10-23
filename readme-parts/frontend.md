## 프론트엔드 (`frontend/`)

Vue 3 + Vite. 로그인, 질문하기(Q&A), 팀 라이브러리, 논문 상세·구조 요약, 설정, 음성 튜터 화면이 있다.

### 실행

```bash
cd frontend
npm install
cp .env.example .env
npm run dev        # http://localhost:5174
```

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VITE_AUTH_URL` | `http://localhost:8080` | 인증서버 |
| `VITE_RAG_URL` | `http://localhost:8001` | RAG·데이터 서비스 |
| `VITE_VOICE_URL` | `http://localhost:8008` | 음성 서비스 |
| `VITE_USE_MOCK` | `true` | 서버 없이 목업 응답으로 동작. 실제 서버와 붙일 때 `false` |

- 토큰은 `Authorization: Bearer`로 보내고 쿠키는 쓰지 않는다. 그래서 세 서비스 모두 CORS 허용 Origin에 `http://localhost:5174`가 있어야 한다.
- 목업 계정: `minsu`(팀원), `admin`(관리자), `rnd`(R&D팀), `noteam`(팀 없음). 비밀번호는 아무 값.

### 배포

```bash
docker build -t referoom-web \
  --build-arg VITE_AUTH_URL=http://localhost:8080 \
  --build-arg VITE_RAG_URL=http://localhost:8001 \
  --build-arg VITE_VOICE_URL=http://localhost:8008 \
  frontend
```

`VITE_*`는 브라우저가 접근하는 주소라서 빌드할 때 넣는다. nginx가 모든 경로에 `index.html`을 돌려줘서 새로고침해도 화면 주소가 유지된다. compose 예: `web: { build: ./frontend, ports: ["5174:80"] }`.
