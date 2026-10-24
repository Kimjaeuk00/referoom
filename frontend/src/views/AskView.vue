<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useQaStore } from '@/stores/qa'
import { useProfileStore } from '@/stores/profile'
import { useLibraryStore } from '@/stores/library'
import { toast } from '@/composables/useToast'
import { clampSide, isNarrow, SIDE_DEFAULT, SIDE_MAX, SIDE_MIN, sideOpen, sideWidth } from '@/composables/useSidePanel'
import { LEVEL_ORDER, LEVELS, levelLabel, VIEWS } from '@/lib/levels'
import { toneOfLabel } from '@/lib/format'
import PaperPicker from '@/components/qa/PaperPicker.vue'
import AnswerView from '@/components/qa/AnswerView.vue'
import StatusBanner from '@/components/common/StatusBanner.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import Icon from '@/components/common/Icon.vue'
import UploadDropzone from '@/components/library/UploadDropzone.vue'
import TopicSearchModal from '@/components/library/TopicSearchModal.vue'
import MicButton from '@/components/voice/MicButton.vue'
import SpeakButton from '@/components/voice/SpeakButton.vue'
import { voiceAvailable } from '@/lib/voice'

const MAX = 1000
const QUICK = [
  'LoRA는 왜 파라미터를 적게 학습해도 되나요?',
  '어텐션에서 √d_k로 나누는 이유는?',
  'QLoRA는 LoRA와 무엇이 다른가요?',
  'RAG는 언제 쓰면 좋은가요?',
]
const timeFmt = new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' })
const SOURCES = [
  ['all', '전체'],
  ['pdf', 'PDF'],
  ['web', '웹'],
]

const qa = useQaStore()
const profile = useProfileStore()
const library = useLibraryStore()
const route = useRoute()
const router = useRouter()

const question = ref('')
const topicOpen = ref(false)
const thread = ref(null)

// 수준·관점의 처음 값은 내 프로필. 여기서 바꾼 값은 질문에만 쓰이고 프로필은 설정 화면에서 바꾼다.
const level = computed({ get: () => qa.level ?? profile.level, set: (v) => (qa.level = v) })
const view = computed({ get: () => qa.view ?? profile.view, set: (v) => (qa.view = v) })

// 왼쪽 목록에서 고른 논문 = 질문 범위. 하나도 없으면 팀 전체.
const pickedIds = computed({
  get: () => (qa.scope.type === 'paper' ? qa.scope.ids : []),
  set: (ids) => (qa.scope = ids.length ? { type: 'paper', ids } : { type: 'all' }),
})

const initial = computed(() => (profile.displayName || '?').slice(0, 1).toUpperCase())
const trimmed = computed(() => question.value.trim())
const canSend = computed(() => trimmed.value.length >= 2 && trimmed.value.length <= MAX && !qa.busy)
const history = computed(() => [...qa.turns].reverse())

onMounted(() => {
  library.refresh()
  // 논문 상세의 "이 논문에 질문하기"로 들어오면 범위를 그 논문으로 맞춘다
  if (route.query.paper) qa.scope = { type: 'paper', ids: [Number(route.query.paper)] }
})

function scopeText(params) {
  const { scope, source } = params
  let text = '팀 전체'
  if (scope?.type === 'tag' && scope.tags?.length) text = `태그 ${scope.tags.join(', ')}`
  if (scope?.type === 'paper' && scope.ids?.length)
    text = scope.ids.length > 1 ? `논문 ${scope.ids.length}편` : library.allPapers.find((p) => p.id === scope.ids[0])?.title ?? String(route.query.title ?? '고른 논문')
  if (source === 'pdf') text += ', PDF만'
  if (source === 'web') text += ', 웹 수집만'
  return text
}

function describe(params) {
  return `${levelLabel(params.level)}, ${VIEWS[params.view]?.name ?? ''} 관점, ${scopeText(params)}`
}

function scrollToTurn(turn, block = 'start') {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(`turn-${turn.id}`)?.scrollIntoView({ block, behavior: reduce ? 'auto' : 'smooth' })
}

async function send() {
  if (!canSend.value) return
  const turn = qa.ask(trimmed.value, { source: qa.source, scope: qa.scope, level: level.value, view: view.value })
  if (!turn) return
  question.value = ''
  if (isNarrow()) sideOpen.value = false // 좁은 화면에서는 서랍을 닫고 답을 보여 준다
  await nextTick()
  scrollToTurn(turn)
}

async function askNow(text) {
  question.value = text
  await send()
}

async function reask(turn, change) {
  const next = qa.ask(turn.question, { ...turn.params, ...change })
  if (!next) return
  await nextTick()
  scrollToTurn(next)
}

function onKeydown(event) {
  // 한글 조합 중에 누른 Enter는 글자 확정이므로 보내지 않는다
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  send()
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

// 왼쪽 패널과 질문 영역 사이 경계를 끌어 너비를 바꾼다. 두 번 누르면 기본 너비로.
const dragging = ref(false)
let dragStart = null

function startDrag(event) {
  dragStart = { x: event.clientX, w: sideWidth.value }
  dragging.value = true
  event.currentTarget.setPointerCapture(event.pointerId)
}

function onDrag(event) {
  if (dragStart) sideWidth.value = clampSide(dragStart.w + event.clientX - dragStart.x)
}

function endDrag() {
  dragStart = null
  dragging.value = false
}

const setSide = (open) => (sideOpen.value = open)
const resetWidth = () => (sideWidth.value = SIDE_DEFAULT)

function onSplitterKey(event) {
  const step = event.shiftKey ? 64 : 16
  const next = { ArrowLeft: sideWidth.value - step, ArrowRight: sideWidth.value + step, Home: SIDE_MIN, End: SIDE_MAX }[event.key]
  if (next === undefined) return
  event.preventDefault()
  sideWidth.value = clampSide(next)
}

// 기록 카드의 상태 문구
function turnState(turn) {
  if (turn.status === 'loading') return '답변을 쓰는 중'
  if (turn.status === 'error') return '답변을 받지 못함'
  if (turn.result?.handoff || !turn.result?.source_details?.length) return '근거를 찾지 못함'
  return null
}
</script>

<template>
  <div class="workspace" :class="{ closed: !sideOpen, dragging }" :style="{ '--side-w': `${sideWidth}px` }">
    <aside id="ask-side" class="side" :inert="!sideOpen" aria-label="논문과 질문 기록">
      <div class="side-inner">
      <div class="panel">
        <PaperPicker v-model="pickedIds" :papers="library.allPapers">
          <UploadDropzone compact input-id="ask-upload" class="upload" @done="library.refresh()" />
        </PaperPicker>
      </div>

      <section class="panel history" aria-labelledby="history-title">
        <h2 id="history-title" class="section-label">이번에 물어본 질문</h2>
        <p v-if="!history.length" class="hint">질문하면 여기에 쌓여요. 누르면 그 답으로 옮겨 가요.</p>
        <button v-for="turn in history" :key="turn.id" type="button" class="card" @click="scrollToTurn(turn)">
          <span class="card-q">{{ turn.question }}</span>
          <span class="card-meta">
            {{ levelLabel(turn.params.level) }}, {{ VIEWS[turn.params.view]?.name }} 관점
            <time class="card-time tabular" :datetime="turn.askedAt.toISOString()">{{ timeFmt.format(turn.askedAt) }}</time>
          </span>
          <span v-if="turnState(turn)" class="card-state">{{ turnState(turn) }}</span>
          <span v-else class="card-pills">
            <span v-for="s in turn.result.source_details" :key="s.label" class="ref" :data-tone="toneOfLabel(s.label)">{{ s.label }}</span>
          </span>
        </button>
      </section>
      </div>
      <div
        class="splitter"
        role="separator"
        aria-orientation="vertical"
        aria-label="논문 목록 너비"
        :aria-valuenow="sideWidth"
        :aria-valuemin="SIDE_MIN"
        :aria-valuemax="SIDE_MAX"
        tabindex="0"
        title="끌어서 너비 조절, 두 번 누르면 원래대로"
        @pointerdown="startDrag"
        @pointermove="onDrag"
        @pointerup="endDrag"
        @pointercancel="endDrag"
        @dblclick="resetWidth"
        @keydown="onSplitterKey"
      />
    </aside>
    <!-- 좁은 화면에서 서랍이 열렸을 때 바깥을 누르면 닫는다 -->
    <div class="scrim" aria-hidden="true" @click="setSide(false)" />

    <section class="main-col">
      <div class="control-bar" role="group" aria-label="질문 조건">
        <span v-if="!sideOpen && pickedIds.length" class="picked-note">논문 {{ pickedIds.length }}편에서 찾는 중</span>
        <div class="control">
          <span class="section-label">설명 수준</span>
          <div class="segmented">
            <button v-for="key in LEVEL_ORDER" :key="key" type="button" :aria-pressed="level === key" :title="LEVELS[key].desc" @click="level = key">
              {{ LEVELS[key].name }}
            </button>
          </div>
        </div>
        <div class="control">
          <span class="section-label">관점</span>
          <div class="segmented">
            <button v-for="(info, key) in VIEWS" :key="key" type="button" :aria-pressed="view === key" :title="info.desc" @click="view = key">
              {{ info.name }}
            </button>
          </div>
        </div>
        <div class="control">
          <span class="section-label">자료</span>
          <div class="segmented">
            <button v-for="[key, name] in SOURCES" :key="key" type="button" :aria-pressed="qa.source === key" @click="qa.source = key">{{ name }}</button>
          </div>
        </div>
      </div>

      <div ref="thread" class="thread" aria-live="polite">
        <EmptyState
          v-if="library.isEmpty && !qa.turns.length"
          title="팀 라이브러리가 비어 있어요"
          text="질문에 답하려면 근거가 될 논문이 있어야 해요. 왼쪽에서 PDF를 올리거나 주제로 논문을 찾아 추가하세요."
        >
          <button type="button" class="btn btn-primary" @click="topicOpen = true">주제로 논문 찾기</button>
        </EmptyState>

        <div v-else-if="!qa.turns.length" class="intro">
          <h1>무엇이 궁금한가요?</h1>
          <p>
            팀 라이브러리<template v-if="library.stats">에 색인된 논문 {{ library.stats.indexed }}편</template>에서 근거를 찾아 답해요.
            왼쪽에서 논문을 고르면 그 논문들에서만 찾고, 답 속 색깔 표시를 누르면 근거가 나온 논문과 쪽수가 보여요.
          </p>
          <!-- Vorb의 "Quick action cards": 누르면 바로 물어본다 -->
          <p class="section-label quick-label">바로 물어보기</p>
          <ul class="quick">
            <li v-for="q in QUICK" :key="q"><button type="button" :disabled="qa.busy" @click="askNow(q)">{{ q }}</button></li>
          </ul>
        </div>

        <article v-for="turn in qa.turns" :id="`turn-${turn.id}`" :key="turn.id" class="turn">
          <div class="msg">
            <span class="avatar user" aria-hidden="true">{{ initial }}</span>
            <div class="msg-body">
              <p class="who">{{ profile.displayName }}</p>
              <p class="q">{{ turn.question }}</p>
            </div>
          </div>

          <div class="msg reply">
            <span class="avatar brand" aria-hidden="true"><Icon name="bookmark" :size="18" /></span>
            <div class="msg-body">
              <p class="who">Referoom <span class="meta">{{ describe(turn.params) }}</span></p>
              <div v-if="turn.status === 'loading'" class="pending">
                <div class="skeleton" aria-hidden="true"><span></span><span></span><span></span></div>
                <p class="hint">{{ turn.slow ? '조금 더 걸리고 있어요.' : '근거를 찾고 답변을 쓰는 중이에요.' }}</p>
              </div>
              <StatusBanner v-else-if="turn.status === 'error'" :message="turn.error.message" :retry="turn.error.retryable" @retry="qa.retry(turn)" />
              <AnswerView
                v-else
                :result="turn.result"
                :params="turn.params"
                :busy="qa.busy"
                @reask="(change) => reask(turn, change)"
                @add-paper="addPaper(turn)"
                @ask-team="askTeam(turn)"
              >
                <SpeakButton v-if="voiceAvailable" :text="turn.result.answer" />
              </AnswerView>
            </div>
          </div>
        </article>
      </div>

      <form class="composer" @submit.prevent="send">
        <div class="composer-box">
          <label class="visually-hidden" for="question">질문</label>
          <textarea
            id="question"
            v-model="question"
            class="composer-input"
            rows="2"
            :maxlength="MAX"
            placeholder="논문에 대해 궁금한 점을 적어 주세요. Enter로 보내고 Shift+Enter로 줄을 바꿔요."
            @keydown="onKeydown"
          ></textarea>
          <div class="composer-foot">
            <label for="ask-upload" class="icon-btn" title="PDF 올리기" @click="setSide(true)">
              <Icon name="clip" /><span class="visually-hidden">PDF 올리기</span>
            </label>
            <button type="button" class="icon-btn" title="주제로 논문 찾기" aria-label="주제로 논문 찾기" @click="topicOpen = true">
              <Icon name="topic" />
            </button>
            <span class="count hint tabular" :class="{ over: trimmed.length > MAX }">{{ trimmed.length }} / {{ MAX }}자</span>
            <MicButton v-if="voiceAvailable" compact :disabled="qa.busy" @transcript="question = $event" />
            <button class="send" type="submit" :disabled="!canSend" :aria-label="qa.busy ? '답변을 기다리는 중' : '질문 보내기'">
              <Icon name="send" :size="18" />
            </button>
          </div>
        </div>
      </form>
    </section>

    <TopicSearchModal :open="topicOpen" :initial-query="trimmed" @close="topicOpen = false" @done="library.refresh()" />
  </div>
</template>

<style scoped>
.workspace {
  display: grid;
  grid-template-columns: var(--side-w) minmax(0, 1fr);
  min-height: calc(100vh - 52px);
  transition: grid-template-columns 0.25s ease;
}

/* ☰로 닫으면 왼쪽 칸 너비가 0으로 줄며 패널이 밀려 들어간다 */
.workspace.closed {
  grid-template-columns: 0 minmax(0, 1fr);
}

.workspace.dragging {
  transition: none;
  cursor: col-resize;
  user-select: none;
}

/* 왼쪽: 회색 바탕 위에 흰 패널 두 개(논문 목록, 질문 기록) */
.side {
  position: sticky;
  top: 52px;
  min-width: 0; /* 안쪽 너비에 막히지 않고 0까지 접히게 */
  height: calc(100vh - 52px);
  overflow: hidden;
  /* Vorb 목록 화면처럼 위는 코랄, 아래로 얼음빛 파랑 */
  background: var(--grad-side);
  border-right: 1px solid var(--c-glass-line);
}

.closed .side {
  border-right-width: 0;
}

/* 안쪽은 너비를 고정해 두어, 접히는 동안 글자가 찌그러지지 않고 잘려 들어간다 */
.side-inner {
  width: var(--side-w);
  height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 16px;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-content: start;
  gap: 16px;
}

/* 경계 손잡이: 평소엔 안 보이고, 가져가면 선이 진해진다 */
.splitter {
  position: absolute;
  top: 0;
  right: 0;
  width: 7px;
  height: 100%;
  cursor: col-resize;
  touch-action: none;
}

.splitter::after {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  width: 3px;
  height: 100%;
  background: transparent;
  transition: background-color 0.15s ease;
}

.splitter:hover::after,
.splitter:focus-visible::after,
.dragging .splitter::after {
  background: var(--c-accent-2);
}

.splitter:focus-visible {
  outline: none;
}

.closed .splitter {
  display: none;
}

.scrim {
  display: none;
}

.picked-note {
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

/* 반투명 흰 카드 */
.panel {
  padding: 14px;
  border: 1px solid var(--c-glass-line);
  border-radius: var(--radius-l);
  background: var(--c-glass);
  backdrop-filter: blur(14px);
}

.upload {
  margin-top: 4px;
}

.history {
  display: grid;
  gap: 8px;
}

.card {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--c-glass-line);
  border-radius: var(--radius-m);
  background: var(--c-glass-strong);
  text-align: left;
  cursor: pointer;
}

.card:hover {
  background: var(--c-paper);
}

.card-q {
  font-size: var(--fs-sm);
  font-weight: 600;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  gap: 8px;
}

/* 시안처럼 카드 오른쪽 아래에 시각을 굵게 */
.card-time {
  margin-left: auto;
  font-weight: 600;
  color: var(--c-ink);
}

.card-meta,
.card-state {
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.card-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* 오른쪽: 조건 줄 → 대화 → 입력창 */
.main-col {
  display: flex;
  flex-direction: column;
  min-width: 0;
  /* Vorb 대화 화면처럼 맨 위만 옅은 코랄, 아래는 얼음빛 파랑 */
  background: var(--grad-top);
}

.control-bar {
  position: sticky;
  top: 52px;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 28px;
  padding: 10px 28px;
  background: var(--c-bar-soft);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--c-glass-line);
}

.control {
  display: flex;
  align-items: center;
  gap: 10px;
}

.control .section-label {
  white-space: nowrap;
}

.control .segmented button {
  min-height: 28px;
  padding: 0 11px;
  font-size: var(--fs-xs);
}

.thread {
  flex: 1;
  width: 100%;
  max-width: 860px;
  padding: 28px 28px 24px;
  display: grid;
  grid-template-columns: minmax(0, 1fr); /* 긴 수식이 열을 밀어 넓히지 않게 */
  align-content: start;
  gap: 28px;
}

.intro {
  max-width: 60ch;
  padding-top: 24px;
}

.intro h1 {
  font-size: 2.75rem;
  line-height: 1.1;
}

.intro p {
  margin-top: 10px;
  color: var(--c-ink-muted);
}

.intro .quick-label {
  margin-top: 28px;
}

/* 회청색 알약 줄: Vorb의 빠른 동작 카드 */
.quick {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
  max-width: 460px;
}

.quick button {
  width: 100%;
  padding: 11px 16px;
  border: 1px solid var(--c-glass-line);
  border-radius: var(--radius-m);
  background: var(--tone3-fill);
  color: var(--c-ink);
  font-size: var(--fs-sm);
  text-align: left;
  cursor: pointer;
}

.quick button:hover:not(:disabled) {
  background: var(--tone1-fill);
}

.quick button:disabled {
  opacity: 0.5;
  cursor: progress;
}

.turn {
  scroll-margin-top: 112px;
  display: grid;
  gap: 14px;
}

/* 말 한 마디 = 피그마 댓글 같은 흰 카드: 동그라미 + 이름 + 내용 */
.msg {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 12px;
  padding: 16px 18px;
  border: 1px solid var(--c-glass-line);
  border-radius: var(--radius-l);
  background: var(--c-glass-strong);
  backdrop-filter: blur(14px);
}

/* 질문 카드는 내용만큼만, 왼쪽 아래 모서리를 뾰족하게(말풍선 꼬리 자리) */
.msg:not(.reply) {
  width: fit-content;
  max-width: 100%;
  border-bottom-left-radius: 4px;
}

.reply {
  padding: 20px 22px 22px;
}

.avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-size: var(--fs-sm);
  font-weight: 600;
}

.avatar.user {
  background: var(--tone0-fill);
  color: var(--tone0-ink);
}

/* 답하는 쪽은 로봇 대신 Referoom 책갈피 */
.avatar.brand {
  border-radius: 50%;
  background: var(--c-black);
  color: var(--c-on-black);
}

.who {
  font-size: var(--fs-sm);
  font-weight: 600;
}

.meta {
  margin-left: 8px;
  font-weight: 400;
  color: var(--c-ink-muted);
  font-size: var(--fs-xs);
}

.q {
  margin-top: 2px;
  font-size: var(--fs-lg);
  font-weight: 500;
  line-height: 1.45;
  letter-spacing: -0.01em;
}

.reply .msg-body > :nth-child(2) {
  margin-top: 12px;
}

.pending {
  max-width: 62ch;
  display: grid;
  gap: 12px;
}

.composer {
  position: sticky;
  bottom: 0;
  padding: 12px 28px 20px;
  background: linear-gradient(transparent, var(--c-bg) 28%);
}

.composer-box {
  max-width: 804px;
  border: 1px solid var(--c-glass-line);
  border-radius: var(--radius-l);
  background: var(--c-glass-strong);
  backdrop-filter: blur(14px);
  box-shadow: var(--shadow-card);
}

.composer-box:focus-within {
  border-color: var(--c-accent-2);
  box-shadow: 0 0 0 1px var(--c-accent-2);
}

.composer-input {
  display: block;
  width: 100%;
  min-height: 64px;
  padding: 12px 14px 4px;
  border: 0;
  border-radius: var(--radius-l) var(--radius-l) 0 0;
  background: none;
  resize: vertical;
  line-height: 1.55;
}

.composer-input:focus-visible {
  outline: none;
}

.composer-foot {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px 8px;
}

.composer-foot .icon-btn {
  color: var(--c-ink-muted);
}

.count {
  margin: 0 10px 0 auto;
}

.over {
  color: var(--c-danger);
}

/* 보내기: 시안의 짙은 동그라미 */
.send {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: var(--c-accent);
  color: var(--c-on-black);
  cursor: pointer;
}

.send:hover:not(:disabled) {
  background: var(--c-accent-ink);
}

.send:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  /* 좁은 화면: 왼쪽에서 밀려 나오는 서랍 */
  .workspace,
  .workspace.closed {
    grid-template-columns: minmax(0, 1fr);
  }

  .side {
    position: fixed;
    top: 52px;
    left: 0;
    bottom: 0;
    z-index: 20;
    width: min(320px, 86vw);
    height: auto;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    box-shadow: var(--shadow-float);
  }

  .workspace:not(.closed) .side {
    transform: none;
  }

  .side-inner {
    width: 100%;
  }

  .splitter {
    display: none;
  }

  .workspace:not(.closed) .scrim {
    display: block;
    position: fixed;
    inset: 52px 0 0;
    z-index: 15;
    background: var(--c-scrim);
  }

  .control-bar {
    padding: 10px 16px;
    gap: 8px 16px;
  }

  .thread {
    padding: 20px 16px;
  }

  .composer {
    padding: 10px 16px 16px;
  }
}
</style>
