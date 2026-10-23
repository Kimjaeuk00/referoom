import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { api, TIMEOUT } from '@/api/client'

// 이번 세션의 질문·답변 기록. 서버에 저장하지 않고 새로고침하면 사라진다(DEV_02 4.2).
// 태그나 논문을 하나도 고르지 않았으면 scope를 보내지 않고 팀 전체로 찾는다
export function scopeBody(scope) {
  const { type, tags = [], ids = [] } = scope ?? {}
  if (type === 'tag' && tags.length) return { type, tags }
  if (type === 'paper' && ids.length) return { type, ids: ids.map(Number) } // paper_id는 숫자(DEV_04 2.1)
  return undefined
}

export const useQaStore = defineStore('qa', () => {
  const turns = ref([])
  const source = ref('all') // pdf | web | all
  const scope = ref({ type: 'all' }) // { type: 'all' } | { type: 'tag', tags } | { type: 'paper', ids }
  const level = ref(null) // null이면 프로필 값을 쓴다
  const view = ref(null)
  const voiceTurns = ref([]) // 음성 튜터 대화 기록, 이 세션에서만

  const busy = computed(() => turns.value.some((t) => t.status === 'loading'))
  let seq = 0

  function requestBody(question, params) {
    return { question, source: params.source, level: params.level, view: params.view, top_k: 5, scope: scopeBody(params.scope) }
  }

  async function run(turn) {
    turn.status = 'loading'
    turn.slow = false
    turn.error = null
    const slowTimer = setTimeout(() => (turn.slow = true), 10_000)
    try {
      turn.result = await api.rag('/rag-query', {
        method: 'POST',
        json: requestBody(turn.question, turn.params),
        timeout: TIMEOUT.query,
      })
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
    const turn = reactive({ id: ++seq, question, params: { ...params }, askedAt: new Date(), status: 'loading', slow: false, result: null, error: null })
    turns.value.push(turn)
    run(turn)
    return turn
  }

  function retry(turn) {
    if (!busy.value) run(turn)
  }

  return { turns, source, scope, level, view, voiceTurns, busy, ask, retry }
})
