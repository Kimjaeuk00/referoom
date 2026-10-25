#!/usr/bin/env bash
set -euo pipefail
set +x
umask 077

fail() {
    printf '[FAIL] %s\n' "$*" >&2
    exit 1
}

pass() {
    printf '[PASS] %s\n' "$*"
}

for tool in curl jq mktemp; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool 설치가 필요합니다."
done

AUTH_URL="${AUTH_URL:-http://localhost:8080}"
RAG_URL="${RAG_URL:-http://localhost:8001}"
AUTH_URL="${AUTH_URL%/}"
RAG_URL="${RAG_URL%/}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-60}"

export E2E_USERNAME="${E2E_USERNAME:-demo_admin}"
export E2E_PASSWORD="${E2E_PASSWORD:-}"
export E2E_OTHER_USERNAME="${E2E_OTHER_USERNAME:-}"
export E2E_OTHER_PASSWORD="${E2E_OTHER_PASSWORD:-}"
export E2E_PAPER_ID="${E2E_PAPER_ID:-}"
export E2E_QUESTION="${E2E_QUESTION:-}"
export E2E_OUT_OF_SCOPE_QUESTION="${E2E_OUT_OF_SCOPE_QUESTION:-}"

for name in E2E_PASSWORD E2E_OTHER_USERNAME E2E_OTHER_PASSWORD \
    E2E_PAPER_ID E2E_QUESTION E2E_OUT_OF_SCOPE_QUESTION; do
    [[ -n "${!name}" ]] || fail "$name 환경변수를 설정하세요."
done

for url in "$AUTH_URL" "$RAG_URL"; do
    case "$url" in
        http://*|https://*) ;;
        *) fail "서버 주소는 http:// 또는 https://로 시작해야 합니다." ;;
    esac
done

[[ "$E2E_PAPER_ID" =~ ^[1-9][0-9]*$ ]] || fail 'E2E_PAPER_ID는 양의 정수여야 합니다.'
[[ "$TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail 'TIMEOUT_SECONDS는 양의 정수여야 합니다.'

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/referoom-e2e.XXXXXX")"
trap 'rm -rf -- "$WORK_DIR"' EXIT
trap 'fail "사용자 또는 시스템이 점검을 중단했습니다."' INT TERM
BODY="$WORK_DIR/response.json"

# 응답·JWT·비밀번호는 출력하지 않고 권한이 제한된 임시 파일로 처리한다.
http() {
    local label="$1" expected="$2" method="$3" url="$4"
    shift 4
    local status
    if ! status="$(curl --disable --silent --show-error \
        --connect-timeout 5 --max-time "$TIMEOUT_SECONDS" \
        --request "$method" --output "$BODY" --write-out '%{http_code}' \
        "$@" -- "$url" 2>"$WORK_DIR/curl-error.txt")"; then
        fail "$label: 연결 실패 또는 제한 시간 초과"
    fi
    [[ "$status" == "$expected" ]] || fail "$label: 예상 HTTP $expected, 실제 $status"
    pass "$label: HTTP $status"
}

check_json() {
    local label="$1" filter="$2"
    shift 2
    jq -e "$@" "$filter" "$BODY" >/dev/null 2>&1 || fail "$label"
    pass "$label"
}

login() {
    local label="$1" credentials="$2" header_file="$3"
    http "$label" 200 POST "$AUTH_URL/api/login" \
        --header 'Content-Type: application/json' --data-binary "@$credentials"
    check_json "$label 응답 계약" '.ok == true and .tokenType == "Bearer"'
    jq -er '
        .accessToken
        | select(type == "string" and test("^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$"))
        | "Authorization: Bearer " + .
    ' "$BODY" >"$header_file" 2>/dev/null || fail "$label: JWT 추출 실패"
}

jq -n '{username: env.E2E_USERNAME, password: env.E2E_PASSWORD}' \
    >"$WORK_DIR/primary-login.json"
jq -n '{username: env.E2E_OTHER_USERNAME, password: env.E2E_OTHER_PASSWORD}' \
    >"$WORK_DIR/other-login.json"
jq -n --argjson paper_id "$E2E_PAPER_ID" '{
    question: env.E2E_QUESTION, source: "pdf",
    scope: {type: "paper", ids: [$paper_id]},
    level: "L2", view: "dev", top_k: 5
}' >"$WORK_DIR/question.json"
jq -n '{
    question: env.E2E_OUT_OF_SCOPE_QUESTION, source: "all",
    scope: {type: "all"}, level: "L2", view: "dev", top_k: 5
}' >"$WORK_DIR/outside.json"

SCHEMA='
    type == "object"
    and (.answer | type == "string" and test("\\S"))
    and (.sources | type == "array" and all(.[]; type == "string" and test("\\S")))
    and (.source_details | type == "array")
    and (.needs_review | type == "boolean")
    and (.handoff | type == "boolean")
    and (.level == "L1" or .level == "L2" or .level == "L3")
    and (.view == "dev" or .view == "rnd")
    and (.latency_ms | type == "number" and . >= 0 and . == floor)
'

# 준비 상태
http 'Java·DB 상태' 200 GET "$AUTH_URL/api/health"
check_json 'Java·DB 정상 응답' '.ok == true and .db == "up"'
http 'RAG 상태' 200 GET "$RAG_URL/health"

# 1. 실제 Java 로그인
login '1. 주 테스트 계정 로그인' "$WORK_DIR/primary-login.json" "$WORK_DIR/primary.headers"
http '주 계정 정보' 200 GET "$AUTH_URL/api/me" --header "@$WORK_DIR/primary.headers"
check_json '주 계정의 팀 가입 확인' '.user.team.id | type == "number" and . > 0 and . == floor'
PRIMARY_TEAM_ID="$(jq -r '.user.team.id' "$BODY")"

# 2. 토큰 없는 요청과 변조 토큰은 모두 차단되어야 한다.
http '2. RAG 무토큰 접근 차단' 401 POST "$RAG_URL/rag-query" \
    --header 'Content-Type: application/json' --data-binary "@$WORK_DIR/question.json"
check_json 'RAG 무토큰 오류 코드' '.code == "UNAUTHORIZED"'
http 'RAG 잘못된 토큰 차단' 401 POST "$RAG_URL/rag-query" \
    --header 'Content-Type: application/json' --header 'Authorization: Bearer invalid-token' \
    --data-binary "@$WORK_DIR/question.json"
check_json 'RAG 잘못된 토큰 오류 코드' '.code == "UNAUTHORIZED"'

# 3. 주 팀에만 적재한 실제 PDF의 답변과 출처 확인
http '3. 인증된 RAG 질문' 200 POST "$RAG_URL/rag-query" \
    --header "@$WORK_DIR/primary.headers" --header 'Content-Type: application/json' \
    --data-binary "@$WORK_DIR/question.json"
check_json 'RAG 응답 기본 형식' "$SCHEMA"
check_json '실제 지정 논문의 답변·페이지 출처' '
    .handoff == false and (.sources | length > 0)
    and any(.source_details[];
        .paper_id == $paper_id
        and (.title | type == "string" and test("\\S"))
        and (.page | type == "number" and . >= 1 and . == floor)
    )
' --argjson paper_id "$E2E_PAPER_ID"

# 4. 라이브러리에 없는 질문은 답을 만들어내지 않아야 한다.
http '4. 문서 밖 질문' 200 POST "$RAG_URL/rag-query" \
    --header "@$WORK_DIR/primary.headers" --header 'Content-Type: application/json' \
    --data-binary "@$WORK_DIR/outside.json"
check_json '문서 밖 질문 응답 형식' "$SCHEMA"
check_json '문서 밖 질문 인계·출처 없음' '
    .handoff == true and (.sources | length == 0) and (.source_details | length == 0)
'

# 5. 주 팀에서 답변 가능했던 같은 논문·같은 질문을 다른 팀 토큰으로 재검사한다.
login '5. 다른 팀 계정 로그인' "$WORK_DIR/other-login.json" "$WORK_DIR/other.headers"
http '다른 팀 계정 정보' 200 GET "$AUTH_URL/api/me" --header "@$WORK_DIR/other.headers"
check_json '다른 계정의 팀 가입 확인' '.user.team.id | type == "number" and . > 0 and . == floor'
OTHER_TEAM_ID="$(jq -r '.user.team.id' "$BODY")"
[[ "$PRIMARY_TEAM_ID" != "$OTHER_TEAM_ID" ]] || fail '팀 격리 검사의 두 계정이 같은 팀입니다.'
pass '두 계정의 서로 다른 team_id 확인'
http '다른 팀의 동일 논문 검색' 200 POST "$RAG_URL/rag-query" \
    --header "@$WORK_DIR/other.headers" --header 'Content-Type: application/json' \
    --data-binary "@$WORK_DIR/question.json"
check_json '다른 팀 응답 형식' "$SCHEMA"
check_json '다른 팀에 논문·출처 비노출' '
    .handoff == true and (.sources | length == 0) and (.source_details | length == 0)
'

printf '[PASS] 필수 API E2E 1~5단계 완료\n'
printf '[INFO] 브라우저 화면·답변 의미 정확성·LLM 미호출 로그·선택 음성은 별도 확인\n'
