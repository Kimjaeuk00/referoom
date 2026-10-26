<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useQaStore } from '@/stores/qa'
import { useProfileStore } from '@/stores/profile'
import { useLibraryStore } from '@/stores/library'
import { toast } from '@/composables/useToast'
import { clampSide, isNarrow, SIDE_DEFAULT, SIDE_MAX, SIDE_MIN, sideOpen, sideWidth } from '@/composables/useSidePanel'
import { depthNote } from '@/lib/levels'
import { MODES } from '@/lib/modes'
import { useModeInput } from '@/composables/useModeInput'
import { useVerifyConsent } from '@/composables/useVerifyConsent'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { toneOfLabel } from '@/lib/format'
import PriorScopeBar from '@/components/qa/PriorScopeBar.vue'
import ModeChips from '@/components/qa/ModeChips.vue'
import ResearchToggle from '@/components/qa/ResearchToggle.vue'
import PaperPicker from '@/components/qa/PaperPicker.vue'
import TurnResult from '@/components/qa/TurnResult.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import Icon from '@/components/common/Icon.vue'
import UploadDropzone from '@/components/library/UploadDropzone.vue'
import TopicSearchModal from '@/components/library/TopicSearchModal.vue'
import MicButton from '@/components/voice/MicButton.vue'
import { voiceAvailable } from '@/lib/voice'

const QUICK = [
  'LoRA는 왜 파라미터를 적게 학습해도 되나요?',
  '어텐션에서 √d_k로 나누는 이유는?',
  'QLoRA는 LoRA와 무엇이 다른가요?',
  'PEFT 기법에는 어떤 방법들이 있고, 각각 어떻게 다른가요?',
]
const timeFmt = new Intl.DateTimeFormat('ko-KR', { hour: '2-digit', minute: '2-digit' })

const qa = useQaStore()
const profile = useProfileStore()
const library = useLibraryStore()
const route = useRoute()
const router = useRouter()

const question = ref('')
const topicOpen = ref(false)
const thread = ref(null)

// 왼쪽 목록에서 고른 논문 = 질문 범위. 하나도 없으면 팀 전체.
const pickedIds = computed({
  get: () => (qa.scope.type === 'paper' ? qa.scope.ids : []),
  set: (ids) => (qa.scope = ids.length ? { type: 'paper', ids } : { type: 'all' }),
})

const initial = computed(() => (profile.displayName || '?').slice(0, 1).toUpperCase())
const { spec, trimmed, reasonText, canSend, max } = useModeInput(question)
const consent = useVerifyConsent()
// 검증은 논문을 고르지 않으면 전체 라이브러리와 비교한다
const modeHint = computed(() => (qa.mode === 'verify' && !pickedIds.value.length ? `${spec.value.hint} 논문을 고르지 않으면 전체 라이브러리에서 찾아요.` : spec.value.hint))
const history = computed(() => [...qa.turns].reverse())

onMounted(() => {
  library.refresh()
  // 논문 상세의 "이 논문에 질문하기"로 들어오면 범위를 그 논문으로 맞춘다
  if (route.query.paper) qa.scope = { type: 'paper', ids: [Number(route.query.paper)] }
  // 논문 상세의 "이 논문으로 주제 찾기"
  if (route.query.mode) qa.setMode(route.query.mode)
})

function scopeText(params) {
  const { scope } = params
  let text = '팀 전체'
  if (scope?.type === 'tag' && scope.tags?.length) text = `태그 ${scope.tags.join(', ')}`
  if (scope?.type === 'paper' && scope.ids?.length)
    text = scope.ids.length > 1 ? `논문 ${scope.ids.length}편` : library.allPapers.find((p) => p.id === scope.ids[0])?.title ?? String(route.query.title ?? '고른 논문')
  return text
}

// 더 쉽게/더 깊게로 다시 물었으면 그 표시 (예: '쉬운 설명')
function describe(params) {
  const mode = params.mode && params.mode !== 'tutor' ? `${MODES[params.mode].label}, ` : ''
  const depth = depthNote(params.level)
  return `${mode}${depth ? `${depth}, ` : ''}${scopeText(params)}`
}

function scrollToTurn(turn, block = 'start') {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(`turn-${turn.id}`)?.scrollIntoView({ block, behavior: reduce ? 'auto' : 'smooth' })
}

function send() {
  if (!canSend.value) return
  consent.guard(qa.mode, submit) // 검증은 처음 한 번 외부 LLM 전송 고지를 보여 준다
}

async function submit() {
  if (qa.needsCollect) {
    qa.priorPending = trimmed.value // 논문을 모으는 창을 열고, 모이면 이어서 보낸다
    question.value = ''
    return
  }
  const turn = qa.ask(trimmed.value, { scope: qa.scope })
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

// 선행연구: 논문을 모으는 창. 모이면 그 논문들을 조사 범위로 삼아 보류한 질문을 보낸다.
const collectOpen = computed(() => topicOpen.value || Boolean(qa.priorPending))
const collectQuery = computed(() => qa.priorPending ?? trimmed.value)

function closeCollect() {
  if (qa.priorPending) question.value = qa.priorPending // 취소하면 질문을 입력창에 돌려 준다
  qa.priorPending = null
  topicOpen.value = false
}

// 체크한 논문이 있어도 새 논문을 더 찾고 싶을 때: 입력한 질문이 있으면 모은 뒤 이어서 보낸다
function collectMore() {
  if (trimmed.value) {
    qa.priorPending = trimmed.value
    question.value = ''
  } else {
    topicOpen.value = true
  }
}

async function onCollected(ids) {
  const pending = qa.priorPending
  if (!pending) return
  qa.priorPending = null
  if (!ids.length) {
    question.value = pending
    toast('수집된 논문이 없어요. 다른 검색어로 다시 찾아 보세요.', { tone: 'error' })
    return
  }
  // 체크한 논문이 있으면 새로 모은 논문을 거기에 더해, 왼쪽 체크가 곧 조사 범위가 되게 한다
  if (pickedIds.value.length) pickedIds.value = [...new Set([...pickedIds.value, ...ids.map(Number)])]
  else qa.priorScope = ids
  const turn = qa.ask(pending, { scope: qa.scope })
  if (!turn) return
  await nextTick()
  scrollToTurn(turn)
}

// 검증에서 근거를 못 찾은 주장: 선행연구 모드로 바꾸고 그 대상 이름을 검색어로 넣는다
function collectFor(claim) {
  qa.setMode('prior')
  qa.priorScope = []
  question.value = claim.subject || claim.sentence
}

function research(turn) {
  qa.priorScope = []
  qa.priorPending = turn.question
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
            {{ MODES[turn.params.mode ?? 'tutor'].label }}
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
          <ResearchToggle :model-value="qa.researchOn" :disabled="qa.busy" @update:model-value="qa.setResearch" />
          <ModeChips v-if="qa.researchOn" :model-value="qa.mode" @update:model-value="qa.setMode" />
        </div>
        <PriorScopeBar v-if="qa.mode === 'prior'" @collect="collectMore" />
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
              <TurnResult
                :turn="turn"
                :busy="qa.busy"
                @retry="qa.retry(turn)"
                @reask="(change) => reask(turn, change)"
                @add-paper="addPaper(turn)"
                @ask-team="askTeam(turn)"
                @research="research(turn)"
                @pick-papers="setSide(true)"
                @collect="collectFor"
              />
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
            :maxlength="max"
            :placeholder="qa.mode === 'tutor' ? '논문에 대해 궁금한 점을 적어 주세요. Enter로 보내고 Shift+Enter로 줄을 바꿔요.' : `${spec.placeholder}. Enter로 보내고 Shift+Enter로 줄을 바꿔요.`"
            :aria-describedby="reasonText ? 'composer-reason' : undefined"
            @keydown="onKeydown"
          ></textarea>
          <div class="composer-foot">
            <label for="ask-upload" class="icon-btn" title="PDF 올리기" @click="setSide(true)">
              <Icon name="clip" /><span class="visually-hidden">PDF 올리기</span>
            </label>
            <button type="button" class="icon-btn" title="주제로 논문 찾기" aria-label="주제로 논문 찾기" @click="topicOpen = true">
              <Icon name="topic" />
            </button>
            <span class="count hint tabular" :class="{ over: trimmed.length > max }">{{ trimmed.length }} / {{ max.toLocaleString('ko-KR') }}자</span>
            <MicButton v-if="voiceAvailable" compact :disabled="qa.busy" @transcript="question = $event" />
            <button class="send" type="submit" :disabled="!canSend" :aria-label="qa.busy ? '답변을 기다리는 중' : '질문 보내기'">
              <Icon name="send" :size="18" />
            </button>
          </div>
        </div>
        <!-- 주제 모드는 안내와 사유가 두 줄이라, 다른 모드도 두 줄 높이를 잡아 입력창 아래 단차를 없앤다 -->
        <div class="mode-notes">
          <p v-if="modeHint" class="hint mode-note">{{ modeHint }}</p>
          <p v-if="reasonText" id="composer-reason" class="hint mode-note" role="status">{{ reasonText }}</p>
        </div>
      </form>
    </section>

    <ConfirmDialog
      :open="consent.open.value"
      title="원고를 외부 AI로 보내요"
      message="입력한 원고가 외부 LLM으로 전송돼요. 로그와 색인에는 저장하지 않아요."
      confirm-label="동의하고 보내기"
      @confirm="consent.confirm"
      @cancel="consent.cancel"
    />
    <TopicSearchModal :open="collectOpen" :initial-query="collectQuery" @close="closeCollect" @done="library.refresh()" @collected="onCollected" />
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

.mode-notes {
  min-height: calc(2 * (1.5 * var(--fs-xs) + 6px));
}

.mode-note {
  margin: 6px 4px 0;
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
