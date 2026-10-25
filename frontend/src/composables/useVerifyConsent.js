import { ref } from 'vue'
import { hasVerifyConsent, rememberVerifyConsent } from '@/lib/consent'

// 검증 모드로 처음 보낼 때 고지 대화상자를 띄우고, 동의하면 이어서 보낸다. 다른 모드는 그대로 통과한다.
export function useVerifyConsent() {
  const open = ref(false)
  let proceed = null

  function guard(mode, go) {
    if (mode !== 'verify' || hasVerifyConsent()) return go()
    proceed = go
    open.value = true
  }

  function confirm() {
    rememberVerifyConsent()
    open.value = false
    const go = proceed
    proceed = null
    go?.()
  }

  function cancel() {
    open.value = false
    proceed = null // 입력창의 원고는 그대로 남아 있다
  }

  return { open, guard, confirm, cancel }
}
