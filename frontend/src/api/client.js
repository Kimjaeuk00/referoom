import { ApiError, normalizeError } from './errors'

// 브라우저가 접근하는 주소. 빌드할 때 VITE_* 값이 들어간다(DEV_02 2절).
export const BASE_URL = {
  auth: import.meta.env.VITE_AUTH_URL || 'http://localhost:8080',
  rag: import.meta.env.VITE_RAG_URL || 'http://localhost:8001',
  voice: import.meta.env.VITE_VOICE_URL || 'http://localhost:8008',
}

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

// 질의 40초, 업로드 요청 자체 60초(색인은 배치 폴링으로 따로 확인한다), 음성 질의는 인식·답변·합성을 합쳐 60초
export const TIMEOUT = { normal: 15_000, query: 40_000, upload: 60_000, voice: 60_000 }

let getToken = () => null
let on = { unauthorized() {}, noTeam() {}, forbidden() {} }

// 라우터·스토어와 순환 참조가 생기지 않게, 앱 시작 시 main.js에서 연결한다
export function configureClient({ getToken: tokenGetter, onUnauthorized, onNoTeam, onForbidden }) {
  getToken = tokenGetter
  on = { unauthorized: onUnauthorized, noTeam: onNoTeam, forbidden: onForbidden }
}

/**
 * 모든 API 호출이 거치는 함수.
 * - Authorization: Bearer <accessToken> 자동 첨부, 쿠키는 쓰지 않는다(credentials: 'omit')
 * - 401 → 토큰 삭제 후 로그인 화면, 403 NO_TEAM → 팀 참여 화면, 403 FORBIDDEN → 토스트
 * - 실패는 ApiError(code, message)로 던진다
 */
export async function apiFetch(baseUrl, path, options = {}) {
  const {
    method = 'GET',
    json,
    formData,
    query,
    signal,
    timeout = TIMEOUT.normal,
    skipAuthRedirect = false, // 로그인·로그아웃처럼 401을 화면이 직접 처리할 때
    as = 'json', // 'blob'이면 응답 본문을 Blob으로 돌려준다(apiBlob)
  } = options

  const url = new URL(path, baseUrl)
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') url.searchParams.set(key, value)
  }

  const headers = { Accept: 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (formData) {
    body = formData // Content-Type은 브라우저가 boundary와 함께 넣는다
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new DOMException('timeout', 'TimeoutError')), timeout)
  const forwardAbort = () => controller.abort(signal.reason)
  signal?.addEventListener('abort', forwardAbort, { once: true })

  let res
  try {
    const init = { method, headers, body, signal: controller.signal, credentials: 'omit' }
    res = USE_MOCK ? await (await import('./mock/index.js')).mockFetch(url, init, BASE_URL) : await fetch(url, init)
  } catch {
    const code = signal?.aborted ? 'ABORTED' : controller.signal.reason?.name === 'TimeoutError' ? 'TIMEOUT' : 'NETWORK'
    throw new ApiError({ status: 0, code })
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', forwardAbort)
  }

  if (res.status === 204) return null
  if (as === 'blob' && res.ok) return res.blob()
  const data = await res.json().catch(() => null)
  if (res.ok && data?.ok !== false) return data

  const error = normalizeError(res.status, data)
  if (res.status === 401 && !skipAuthRedirect) on.unauthorized()
  else if (res.status === 403 && error.code === 'NO_TEAM') on.noTeam()
  else if (res.status === 403) on.forbidden(error)
  throw error
}

export const api = {
  auth: (path, options) => apiFetch(BASE_URL.auth, path, options),
  rag: (path, options) => apiFetch(BASE_URL.rag, path, options),
  voice: (path, options) => apiFetch(BASE_URL.voice, path, options),
}

// <audio src>에는 Authorization 헤더를 붙일 수 없어서, Bearer로 받아 Blob으로 넘긴다(DEV_02 3.2)
export function apiBlob(baseUrl, path, options = {}) {
  return apiFetch(baseUrl, path, { ...options, as: 'blob' })
}
