// 검증 모드의 "원고가 외부 LLM으로 전송돼요" 고지에 동의했는지. 동의 여부 하나만 기억하고 원고 내용은 어디에도 저장하지 않는다.
// 저장소가 막혀 있으면 기억하지 못하므로 그 경우엔 보낼 때마다 묻는다.
export const VERIFY_CONSENT_KEY = 'referoom.verify-consent'

export function hasVerifyConsent(storage = globalThis.localStorage) {
  try {
    return storage.getItem(VERIFY_CONSENT_KEY) === '1'
  } catch {
    return false
  }
}

export function rememberVerifyConsent(storage = globalThis.localStorage) {
  try {
    storage.setItem(VERIFY_CONSENT_KEY, '1')
  } catch {
    /* 기억하지 못하면 다음에도 묻는다 */
  }
}
