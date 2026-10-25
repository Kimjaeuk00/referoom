// 서버 에러 code → 사용자에게 보여줄 문구. 서버 detail은 그대로 보여주지 않는다(DEV_02 3.2).
// AI 서비스: {detail, code} / 인증서버(Java): {ok:false, error, code} (DEV_01 3.4)
const MESSAGES = {
  UNAUTHORIZED: '로그인이 필요해요.',
  TOKEN_EXPIRED: '로그인 시간이 끝났어요. 다시 로그인해 주세요.',
  INVALID_CREDENTIALS: '아이디 또는 비밀번호가 올바르지 않아요',
  NO_TEAM: '팀에 참여한 뒤에 쓸 수 있어요.',
  FORBIDDEN: '권한이 없습니다',
  NOT_FOUND: '찾는 항목이 없어요.',
  TEAM_NOT_FOUND: '이 초대 코드로 찾은 팀이 없어요. 코드를 다시 확인해 주세요.',
  ALREADY_IN_TEAM: '이미 팀에 속해 있어요.',
  CONFLICT: '이미 등록된 항목이에요.',
  ZOTERO_AUTH_FAILED: 'Zotero에 연결하지 못했어요. 그룹 ID와 API Key를 확인해 주세요.',
  PAYLOAD_TOO_LARGE: '파일이 너무 커요. PDF는 20MB까지 올릴 수 있어요.',
  VALIDATION_ERROR: '입력한 내용을 확인해 주세요.',
  STT_EMPTY: '음성을 알아듣지 못했어요. 다시 말해 주세요.',
  RATE_LIMITED: '요청이 많아 잠시 쉬고 있어요. 조금 뒤에 다시 시도해 주세요.',
  NOT_READY: '서비스를 준비 중이에요. 잠시 후 다시 시도해 주세요.',
  UPSTREAM_TIMEOUT: '응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.',
  TIMEOUT: '응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.',
  NETWORK: '서버에 연결할 수 없어요',
  ABORTED: '요청을 취소했어요.',
  UNKNOWN: '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.',
}

const CODE_BY_STATUS = {
  400: 'VALIDATION_ERROR',
  401: 'UNAUTHORIZED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  413: 'PAYLOAD_TOO_LARGE',
  422: 'VALIDATION_ERROR',
  429: 'RATE_LIMITED',
  503: 'NOT_READY',
  504: 'UPSTREAM_TIMEOUT',
}

const RETRYABLE = new Set(['NOT_READY', 'UPSTREAM_TIMEOUT', 'TIMEOUT', 'NETWORK', 'UNKNOWN'])

export class ApiError extends Error {
  constructor({ status = 0, code = 'UNKNOWN', fields = [] } = {}) {
    super(MESSAGES[code] ?? MESSAGES.UNKNOWN)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields // 422일 때 문제가 된 입력 이름 목록
    this.retryable = RETRYABLE.has(code)
  }
}

function fieldsOf(data) {
  if (Array.isArray(data?.detail)) {
    // FastAPI 기본 검증 응답: [{ loc: ['body', 'question'], ... }]
    return data.detail.map((d) => (Array.isArray(d?.loc) ? d.loc[d.loc.length - 1] : null)).filter(Boolean)
  }
  if (data?.fields && typeof data.fields === 'object') return Object.keys(data.fields)
  return []
}

export function normalizeError(status, data) {
  const code = typeof data?.code === 'string' && data.code ? data.code : CODE_BY_STATUS[status] ?? 'UNKNOWN'
  return new ApiError({ status, code, fields: fieldsOf(data) })
}

// 화면마다 같은 code를 다르게 말해야 할 때 쓴다. 예: 회원가입의 CONFLICT → "이미 쓰고 있는 아이디예요"
export function errorText(error, overrides = {}) {
  if (error instanceof ApiError) return overrides[error.code] ?? error.message
  return MESSAGES.UNKNOWN
}
