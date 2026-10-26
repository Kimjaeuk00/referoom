import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { api, TIMEOUT } from '@/api/client'
import { buildRequest, CHIP_MODES, isMode, manuscriptPreview } from '@/lib/modes'

// 이번 세션의 질문·답변 기록. 서버에 저장하지 않고 새로고침하면 사라진다(DEV_02 4.2).
// 태그나 논문을 하나도 고르지 않았으면 scope를 보내지 않고 팀 전체로 찾는다
export function scopeBody(scope) {
  const { type, tags = [], ids = [] } = scope ?? {}
  if (type === 'tag' && tags.length) return { type, tags }
  if (type === 'paper' && ids.length) return { type, ids: ids.map(Number) } // paper_id는 숫자(DEV_04 2.1)
  return undefined
}

const MODE_KEY = 'referoom.mode' // 마지막으로 고른 모드만 기억한다. 질문·원고 같은 입력 내용은 저장하지 않는다
function loadMode() {
  try {
    const saved = localStorage.getItem(MODE_KEY)
    return isMode(saved) ? saved : 'prior' // 처음 열면 연구 모드가 켜진 상태(선행연구)다. 끄고 나간 사람은 튜터로 기억된다
  } catch {
    return 'prior' // 저장소가 막혀 있어도 기본값(연구 모드 켜짐)으로 동작한다
  }
}

export const useQaStore = defineStore('qa', () => {
  const turns = ref([])
  const scope = ref({ type: 'all' }) // { type: 'all' } | { type: 'tag', tags } | { type: 'paper', ids }
  const mode = ref(loadMode()) // tutor | prior | topic | verify. 기본은 연구 모드가 켜진 prior이고, 스위치를 끄면 tutor다
  const lastResearch = ref(CHIP_MODES.includes(mode.value) ? mode.value : 'prior') // 연구 모드를 다시 켤 때 돌아갈 모드
  const priorScope = ref([]) // 선행연구에서 수집한 논문 id. 새로고침하면 사라진다
  const libraryOnly = ref(false) // 선행연구에서 논문을 새로 찾지 않고 라이브러리 안에서만 찾기
  const priorPending = ref(null) // 논문을 모으는 동안 보류 중인 선행연구 질문
  const voiceTurns = ref([]) // 음성 튜터 대화 기록, 이 세션에서만

  const busy = computed(() => turns.value.some((t) => t.status === 'loading'))
  let seq = 0

  // level은 '더 쉽게/더 깊게'로 다시 물을 때만 body에 들어간다. 설정으로 저장하지 않는다(기능명세서 F2-2a, lib/modes.js 테스트 참고).
  function setMode(next) {
    mode.value = isMode(next) ? next : 'tutor'
    if (CHIP_MODES.includes(mode.value)) lastResearch.value = mode.value
    try {
      localStorage.setItem(MODE_KEY, mode.value)
    } catch {
      /* 저장하지 못해도 이번 화면에서는 그대로 쓴다 */
    }
  }

  // 연구 모드 스위치: 켜면 마지막에 쓴 연구 모드(처음엔 선행연구), 끄면 튜터
  const researchOn = computed(() => mode.value !== 'tutor')
  const setResearch = (on) => setMode(on ? lastResearch.value : 'tutor')

  // 주제·검증의 대상 논문 = 왼쪽 목록에서 고른 논문
  const pickedIds = computed(() => (scope.value.type === 'paper' ? scope.value.ids : []))

  // 선행연구는 조사 범위(왼쪽에서 체크한 논문이나 수집한 논문)가 없으면 질문을 보내기 전에 논문부터 찾아 모은다
  const needsCollect = computed(() => mode.value === 'prior' && !libraryOnly.value && pickedIds.value.length === 0 && priorScope.value.length === 0)

  function request(turn) {
    const { mode: m = 'tutor', scope: s, level, paperIds, priorIds } = turn.params
    // 검증은 원고 전체(turn.manuscript)를 보내고 화면에는 요약(turn.question)만 둔다
    return buildRequest(m, { question: turn.manuscript ?? turn.question, scope: scopeBody(s), level, paperIds, priorIds })
  }

  async function run(turn) {
    turn.status = 'loading'
    turn.slow = false
    turn.error = null
    const slowTimer = setTimeout(() => (turn.slow = true), 10_000)
    try {
      const { path, body, timeoutKey } = request(turn)
      turn.result = await api.rag(path, { method: 'POST', json: body, timeout: TIMEOUT[timeoutKey] })
      turn.status = 'done'
    } catch (error) {
      turn.error = error
      turn.status = 'error'
    } finally {
      clearTimeout(slowTimer)
    }
  }

  function ask(question, params) {
    if (busy.value) return null
    // 체크한 논문이 있으면 예전에 수집한 범위보다 체크한 논문이 우선이라 priorIds를 비운다
    // 보낸 뒤에 모드를 바꿔도 이 질문은 그대로이도록, 모드와 대상 논문을 질문에 박아 둔다
    const fixed = { mode: mode.value, paperIds: [...pickedIds.value], priorIds: libraryOnly.value || pickedIds.value.length ? [] : [...priorScope.value], ...params }
    // 원고는 이 세션의 메모리에만 두고 어디에도 저장하지 않는다. '다시 시도'에 필요해서 turn.manuscript에 보관한다.
    const isVerify = fixed.mode === 'verify'
    const turn = reactive({ id: ++seq, question: isVerify ? manuscriptPreview(question) : question, manuscript: isVerify ? question : undefined, params: fixed, askedAt: new Date(), status: 'loading', slow: false, result: null, error: null })
    turns.value.push(turn)
    run(turn)
    return turn
  }

  function retry(turn) {
    if (!busy.value) run(turn)
  }

  return { turns, scope, mode, researchOn, setResearch, priorScope, libraryOnly, priorPending, needsCollect, pickedIds, voiceTurns, busy, setMode, ask, retry }
})
