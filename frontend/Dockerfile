# 1단계: 빌드. VITE_* 값은 브라우저가 접근하는 주소(호스트 기준)라서 빌드할 때 넣는다.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_AUTH_URL=http://localhost:8080
ARG VITE_RAG_URL=http://localhost:8001
ARG VITE_VOICE_URL=http://localhost:8008
ARG VITE_USE_MOCK=false
ENV VITE_AUTH_URL=$VITE_AUTH_URL \
    VITE_RAG_URL=$VITE_RAG_URL \
    VITE_VOICE_URL=$VITE_VOICE_URL \
    VITE_USE_MOCK=$VITE_USE_MOCK
RUN npm run build

# 2단계: nginx로 정적 파일 서빙 (compose: web: ports ["5174:80"])
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
