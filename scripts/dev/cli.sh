#!/usr/bin/env bash
# Shared CLI functions. This file is sourced by scripts/dev.sh (Bash 3.2+).

dev_usage() {
    cat <<'USAGE'
사용법: scripts/dev.sh <명령> [서비스...]

현재 단계: B3 — 로컬 개발 환경 관리 (Python 3.11 필요)

  setup                 Python 3.11 환경 및 서비스 의존성 준비
  init-env              없는 경우에만 공통 JWT_SECRET 생성
  up [서비스...]        서비스 실행
  down [서비스...]      이 스크립트가 관리하는 프로세스 종료
  status                서비스 실행 및 준비 상태 확인
  logs <서비스>         서비스 로그 보기
  restart <서비스>      서비스 재시작
  test                  서비스별 테스트 실행 및 결과 요약
  help, -h, --help      이 도움말 표시

서비스: db, auth, rag, voice, frontend
실행 기록: .run/pids, .run/logs (Git 제외)
setup은 의존성을 설치합니다. 기존 .env와 프론트 lockfile을 덮어쓰지 않습니다.
test의 Python 테스트는 외부 네트워크를 차단합니다. 실제 유료 API 검증은 별도 승인 대상입니다.
기존 포트를 강제 종료하지 않습니다. up 실패 시 이미 시작한 서비스는 status/down으로 관리하세요.
USAGE
}

dev_error() {
    printf '[ERROR] %s\n' "$1" >&2
}
