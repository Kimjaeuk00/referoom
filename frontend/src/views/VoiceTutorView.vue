<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, TIMEOUT } from '@/api/client'
import { errorText } from '@/api/errors'
import { scopeBody, useQaStore } from '@/stores/qa'
import { useProfileStore } from '@/stores/profile'
import { useLibraryStore } from '@/stores/library'
import { toast } from '@/composables/useToast'
import { audioFileName, audioUrl, BAR_WEIGHTS, barPx, MAX_RECORD_SECONDS, micErrorText, micFeedback, useAudioPlayer, useRecorder } from '@/lib/voice'
import ScopeSelector from '@/components/qa/ScopeSelector.vue'
import AnswerView from '@/components/qa/AnswerView.vue'
import ViewSelector from '@/components/common/ViewSelector.vue'

// 음성 튜터(DEV_04 7절): 말로 묻고 → POST /voice-qa 한 번에 인식·답변·합성 → 답을 읽어 준다.
// 관점·범위는 Q&A 화면과 같은 값을 쓴다.
const qa = useQaStore()
const profile = useProfileStore()
const library = useLibraryStore()
const router = useRouter()
const recorder = useRecorder()
const player = useAudioPlayer()

const view = computed({ get: () => qa.view ?? profile.view, set: (v) => (qa.view = v) })

const thinking = ref(false)
const error = ref('')
const seconds = ref(0)
let tick = null
let seq = 0

const current = computed(() => qa.voiceTurns.at(-1) ?? null)
const earlier = computed(() => qa.voiceTurns.slice(0, -1).reverse())

// 서버 한 번 호출 안에서 인식과 답변 생성이 같이 일어나서, 그 둘은 한 단계로 보여 준다
const phase = computed(() => {
  if (recorder.state.value === 'recording') return 'listening'
  if (thinking.value) return 'thinking'
  if (player.playing.value) return 'speaking'
  return 'idle'
})
const PHASE_TEXT = {
  idle: '버튼을 누르고 질문을 말하세요.',
  listening: '듣는 중이에요. 다 말했으면 버튼을 한 번 더 누르세요.',
  thinking: '질문을 알아듣고 답변을 만드는 중이에요.',
  speaking: '답변을 읽는 중이에요.',
}

// 듣는 동안 마이크에 소리가 실제로 들어오는지: 막대는 입력 음량, 문구는 목소리 유무를 보여 준다
const feedback = computed(() => micFeedback({ speaking: recorder.speaking.value, silentMs: recorder.silentMs.value }))
const MIC_TEXT = {
  hearing: '인식 중이에요',
  waiting: '말씀해 주세요',
  quiet: '소리가 들리지 않아요. 마이크 연결과 입력 볼륨을 확인해 주세요.',
}
const barHeight = (weight) => `${barPx(recorder.level.value, weight)}px`

const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

onMounted(() => library.refresh())

async function press() {
  if (phase.value === 'listening') return ask()
  if (phase.value === 'speaking') player.stop()
  error.value = ''
  try {
    await recorder.start()
  } catch (e) {
    error.value = micErrorText(e)
    return
  }
  seconds.value = 0
  tick = setInterval(() => {
    seconds.value += 1
    if (seconds.value >= MAX_RECORD_SECONDS) ask()
  }, 1000)
}

async function ask() {
  clearInterval(tick)
  thinking.value = true
  try {
    const blob = await recorder.stop()
    const form = new FormData()
    form.append('audio', blob, audioFileName(blob))
    form.append('view', view.value)
    form.append('source', qa.source)
    const scope = scopeBody(qa.scope)
    if (scope) form.append('scope', JSON.stringify(scope))
    form.append('speak', 'true')
    const params = { view: view.value, source: qa.source, scope: qa.scope }
    const result = await api.voice('/voice-qa', { method: 'POST', formData: form, timeout: TIMEOUT.voice })
    qa.voiceTurns.push({ id: ++seq, question: result.stt_text, result, params })
    thinking.value = false
    if (result.audio_url) await play(result.audio_url)
  } catch (e) {
    error.value = errorText(e, {
      STT_EMPTY: '말소리를 알아듣지 못했어요. 조금 더 가까이에서 다시 말해 주세요.',
      TIMEOUT: '답변이 60초 안에 오지 않았어요. 질문을 짧게 나눠 다시 말해 주세요.',
    })
  } finally {
    thinking.value = false
  }
}

async function play(path) {
  try {
    await player.play(audioUrl(path))
  } catch (e) {
    error.value = errorText(e)
  }
}

function addPaper(turn) {
  router.push({ name: 'library', query: { topic: turn.question } })
}

async function askTeam(turn) {
  try {
    await navigator.clipboard.writeText(turn.question)
    toast('질문을 복사했어요. 팀 채널에 붙여 넣어 물어보세요.')
  } catch {
    toast('복사하지 못했어요. 질문을 직접 선택해 복사하세요.', { tone: 'error' })
  }
}

onBeforeUnmount(() => {
  clearInterval(tick)
  if (recorder.state.value === 'recording') recorder.stop().catch(() => {})
  player.stop()
})
</script>

<template>
  <div class="voice">
    <aside class="controls" aria-label="질문 조건">
      <ScopeSelector v-model:source="qa.source" v-model:scope="qa.scope" :papers="library.allPapers" :tags="library.tags" />
      <ViewSelector v-model:view="view" :disabled="phase === 'listening' || phase === 'thinking'" />
    </aside>

    <section class="column">
      <h1>말로 묻기</h1>
      <p class="hint">마이크는 localhost나 https 주소에서만 켜져요. 한 번에 {{ MAX_RECORD_SECONDS }}초까지 들어요.</p>

      <div class="stage" :class="phase">
        <button
          type="button"
          class="mic"
          :aria-pressed="phase === 'listening'"
          :disabled="phase === 'thinking'"
          @click="press"
        >
          <span class="visually-hidden">{{ phase === 'listening' ? '말하기 끝' : '말하기 시작' }}</span>
        </button>
        <p class="phase" role="status">{{ PHASE_TEXT[phase] }}</p>
        <div v-if="phase === 'listening' && recorder.meterOn.value" class="meter" :class="feedback">
          <span class="bars" aria-hidden="true"><i v-for="(w, n) in BAR_WEIGHTS" :key="n" :style="{ height: barHeight(w) }" /></span>
          <p class="mic-status" :role="feedback === 'quiet' ? 'alert' : undefined">{{ MIC_TEXT[feedback] }}</p>
        </div>
        <!-- 음량을 못 재는 환경: 숨기지 않고 알려 준다. 녹음 자체는 진행 중이다 -->
        <p v-else-if="phase === 'listening'" class="mic-status">입력 음량은 표시할 수 없지만 녹음은 진행 중이에요.</p>
        <p v-if="phase === 'listening'" class="timer tabular">{{ clock(seconds) }} / {{ clock(MAX_RECORD_SECONDS) }}</p>
        <p v-if="error" class="field-error" role="alert">{{ error }}</p>
      </div>

      <article v-if="current" class="turn">
        <header class="turn-head">
          <p class="label">들은 질문</p>
          <p class="turn-q">{{ current.question }}</p>
        </header>
        <AnswerView :result="current.result" :params="current.params" :reaskable="false" @add-paper="addPaper(current)" @ask-team="askTeam(current)">
          <button v-if="current.result.audio_url" type="button" class="btn" :disabled="phase !== 'idle' && phase !== 'speaking'" @click="phase === 'speaking' ? player.stop() : play(current.result.audio_url)">
            {{ phase === 'speaking' ? '그만 듣기' : '다시 듣기' }}
          </button>
        </AnswerView>
        <!-- 출처가 없으면 AnswerView가 handoff 안내를 보여 준다. 낭독 문구는 음성 서비스의 speech_text -->
        <div v-if="current.result.handoff && current.result.audio_url" class="replay">
          <button type="button" class="btn" :disabled="phase !== 'idle' && phase !== 'speaking'" @click="phase === 'speaking' ? player.stop() : play(current.result.audio_url)">
            {{ phase === 'speaking' ? '그만 듣기' : '안내 다시 듣기' }}
          </button>
        </div>
      </article>

      <section v-if="earlier.length" class="history" aria-labelledby="voice-history">
        <h2 id="voice-history">앞서 물은 질문</h2>
        <details v-for="turn in earlier" :key="turn.id" class="past">
          <summary>{{ turn.question }}</summary>
          <AnswerView :result="turn.result" :params="turn.params" :reaskable="false" @add-paper="addPaper(turn)" @ask-team="askTeam(turn)" />
        </details>
      </section>
    </section>
  </div>
</template>

<style scoped>
.voice {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 48px;
  padding-bottom: 48px;
}

.controls {
  position: sticky;
  top: 88px;
  align-self: start;
  display: grid;
  gap: 28px;
}

.column {
  min-width: 0;
}

h1 {
  font-size: var(--fs-2xl);
}

.column > .hint {
  margin-top: 6px;
}

.stage {
  margin: 32px 0 40px;
  display: grid;
  justify-items: center;
  gap: 12px;
  text-align: center;
}

/* 마이크 버튼: 평소엔 초록 원, 듣는 동안은 빨간 원 + 바깥 고리 */
.mic {
  width: 96px;
  height: 96px;
  border: 0;
  border-radius: 50%;
  background: var(--c-accent);
  box-shadow: 0 0 0 6px var(--c-accent-wash);
  cursor: pointer;
  display: grid;
  place-items: center;
}

.mic::before {
  content: "";
  width: 22px;
  height: 34px;
  border-radius: 11px;
  background: var(--c-paper);
}

.mic:disabled {
  opacity: 0.55;
  cursor: progress;
}

.listening .mic {
  background: var(--c-danger);
  box-shadow: 0 0 0 6px color-mix(in srgb, var(--c-danger) 18%, transparent);
}

.listening .mic::before {
  width: 26px;
  height: 26px;
  border-radius: 4px;
}

@media (prefers-reduced-motion: no-preference) {
  .listening .mic {
    animation: ring 1.6s ease-out infinite;
  }
}

@keyframes ring {
  50% {
    box-shadow: 0 0 0 14px color-mix(in srgb, var(--c-danger) 10%, transparent);
  }
}

.phase {
  font-weight: 500;
}

/* 입력 음량 표시: 막대는 들어오는 소리 크기, 문구는 인식 중 / 기다리는 중 / 소리 없음 */
.meter {
  display: grid;
  justify-items: center;
  gap: 6px;
}

.bars {
  height: 36px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.bars i {
  width: 5px;
  border-radius: 3px;
  background: var(--c-ink-muted);
  transition: height 80ms linear, background-color 150ms;
}

.mic-status {
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}

.meter.hearing .bars i {
  background: var(--c-ok);
}

.meter.hearing .mic-status {
  color: var(--c-ok);
  font-weight: 600;
}

.meter.hearing .mic-status::before {
  content: "● ";
}

.meter.quiet .mic-status {
  color: var(--c-danger);
  font-weight: 600;
}

.timer {
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
}

.turn-head {
  margin-bottom: 16px;
  padding-left: 14px;
  border-left: 3px solid var(--c-accent);
}

.turn-q {
  margin-top: 2px;
  font-size: var(--fs-lg);
  font-weight: 600;
  line-height: var(--lh-tight);
}

.replay {
  margin-top: 12px;
}

.history {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--c-rule);
  display: grid;
  gap: 8px;
}

.history h2 {
  font-size: var(--fs-md);
}

.past summary {
  padding: 8px 0;
  cursor: pointer;
}

.past[open] summary {
  margin-bottom: 12px;
}

@media (max-width: 900px) {
  .voice {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .controls {
    position: static;
  }
}
</style>
