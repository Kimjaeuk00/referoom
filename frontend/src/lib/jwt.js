// 토큰 payload는 화면 표시와 라우트 가드에만 쓴다. 서명 검증은 서버 몫이다(DEV_02 3.1).
export function decodeJwt(token) {
  const part = typeof token === 'string' ? token.split('.')[1] : null
  if (!part) return null
  try {
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0))
    return JSON.parse(new TextDecoder().decode(bytes))
  } catch {
    return null
  }
}

export function isExpired(claims, now = Date.now()) {
  return !claims || typeof claims.exp !== 'number' || claims.exp * 1000 <= now
}
