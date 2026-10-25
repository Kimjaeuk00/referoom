import { computed, unref } from 'vue'
import { MODES, validateInput } from '@/lib/modes'
import { useQaStore } from '@/stores/qa'

// 질문 입력창(홈·질문 화면 공통): 현재 모드에 맞는 안내 문구·글자 수 제한·전송 조건.
// 주제·검증은 왼쪽 목록에서 고른 논문(qa.scope)을 대상 논문으로 쓴다.
export function useModeInput(question) {
  const qa = useQaStore()
  const spec = computed(() => MODES[qa.mode])
  const trimmed = computed(() => unref(question).trim())
  const reason = computed(() => validateInput(qa.mode, trimmed.value, qa.pickedIds))
  const canSend = computed(() => reason.value === null && !qa.busy)
  // 빈 입력창에 "2자 이상 입력하세요"를 띄우지 않는다. 대상 논문이 필요한 주제 모드는 처음부터 알려 준다.
  const reasonText = computed(() => (reason.value && (trimmed.value.length > 0 || qa.mode === 'topic') ? reason.value : ''))
  return { spec, trimmed, reason, reasonText, canSend, max: computed(() => spec.value.max) }
}
