<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQaStore } from '@/stores/qa'
import { useProfileStore } from '@/stores/profile'
import { useLibraryStore } from '@/stores/library'
import { sideOpen } from '@/composables/useSidePanel'
import { VIEWS } from '@/lib/levels'
import { voiceAvailable } from '@/lib/voice'
import Icon from '@/components/common/Icon.vue'
import ViewSelector from '@/components/common/ViewSelector.vue'
import TopicSearchModal from '@/components/library/TopicSearchModal.vue'
import MicButton from '@/components/voice/MicButton.vue'
import { formatDate } from '@/lib/format'

// 로그인 뒤 첫 화면: 인사말 하나와 질문 입력창 하나. 보내면 질문하기 화면으로 넘어가 답을 받는다.
const MAX = 1000
const EXAMPLES = ['LoRA는 왜 파라미터를 적게 학습해도 되나요?', '어텐션에서 √d_k로 나누는 이유는?']

const qa = useQaStore()
const profile = useProfileStore()
const library = useLibraryStore()
const router = useRouter()

const question = ref('')
const input = ref(null)
const plusMenu = ref(null)
const condMenu = ref(null)
const topicOpen = ref(false)

const view = computed({ get: () => qa.view ?? profile.view, set: (v) => (qa.view = v) })
const trimmed = computed(() => question.value.trim())
const canSend = computed(() => trimmed.value.length >= 2 && trimmed.value.length <= MAX && !qa.busy)
const name = computed(() => profile.displayName)

// 시안의 기울어진 파스텔 숫자 카드: 우리 팀 라이브러리의 실제 숫자
const facts = computed(() => {
  const s = library.stats
  if (!s) return []
  const chunks = Object.values(s.chunks ?? {}).reduce((a, b) => a + b, 0)
  return [
    { big: `${s.papers}편`, text: '팀 라이브러리 논문', tone: 'tone-1' },
    { big: `${s.indexed}편`, text: '질문에 쓸 수 있는 논문', tone: 'tone-0' },
    { big: chunks.toLocaleString('ko-KR'), text: '근거로 찾는 글 조각', tone: 'tone-2' },
    { big: s.last_synced_at ? formatDate(s.last_synced_at) : '아직', text: 'Zotero 마지막 동기화', tone: 'tone-3' },
  ]
})

onMounted(() => {
  library.refresh()
  input.value?.focus()
  document.addEventListener('pointerdown', closeMenus)
})
onBeforeUnmount(() => document.removeEventListener('pointerdown', closeMenus))

// 바깥을 누르면 열린 작은 메뉴(+, 조건)를 닫는다
function closeMenus(event) {
  for (const d of [plusMenu.value, condMenu.value]) if (d?.open && !d.contains(event.target)) d.open = false
}

function send() {
  if (!canSend.value) return
  const turn = qa.ask(trimmed.value, { source: qa.source, scope: qa.scope, view: view.value })
  if (turn) router.push({ name: 'ask' })
}

function onKeydown(event) {
  // 한글 조합 중에 누른 Enter는 글자 확정이므로 보내지 않는다
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  send()
}

function openPapers() {
  sideOpen.value = true
  router.push({ name: 'ask' })
}
</script>

<template>
  <div class="home glow-bg">
    <div class="center">
      <h1 class="greeting">{{ name ? `${name}님, ` : '' }}어떤 논문이 궁금한가요?</h1>

      <form class="ask-pill" @submit.prevent="send">
        <!-- +: 논문을 더하거나 고르는 일 -->
        <details ref="plusMenu" class="menu-wrap">
          <summary class="icon-btn plus" aria-label="논문 추가와 범위"><Icon name="plus" :size="22" /></summary>
          <div class="pop" role="menu">
            <RouterLink role="menuitem" :to="{ name: 'library', query: { upload: 1 } }"><Icon name="upload" :size="18" /> PDF 올리기</RouterLink>
            <button role="menuitem" type="button" @click="topicOpen = true; plusMenu.open = false"><Icon name="topic" :size="18" /> 주제로 논문 찾기</button>
            <button role="menuitem" type="button" @click="openPapers"><Icon name="doc" :size="18" /> 논문 골라서 묻기</button>
          </div>
        </details>

        <label class="visually-hidden" for="home-q">질문</label>
        <textarea
          id="home-q"
          ref="input"
          v-model="question"
          class="q-input"
          rows="1"
          :maxlength="MAX"
          placeholder="논문에 대해 궁금한 점을 물어보세요"
          @keydown="onKeydown"
        ></textarea>

        <!-- 시안의 "Pro 높음" 자리: 답변 관점 (모드 칩은 T5에서 이 아래에 들어간다) -->
        <details ref="condMenu" class="menu-wrap">
          <summary class="cond">
            <span class="cond-view">{{ VIEWS[view]?.name }} 관점</span>
            <Icon name="chevron" :size="18" />
          </summary>
          <div class="pop cond-pop">
            <ViewSelector v-model:view="view" />
          </div>
        </details>

        <MicButton v-if="voiceAvailable" compact :disabled="qa.busy" @transcript="question = $event" />
        <button class="send" type="submit" :disabled="!canSend" aria-label="질문 보내기"><Icon name="send" :size="18" /></button>
      </form>

      <p v-if="library.isEmpty" class="note">
        팀 라이브러리가 아직 비어 있어요. <button type="button" class="link" @click="topicOpen = true">주제로 논문 찾기</button>로 먼저 논문을 모아 주세요.
      </p>
      <div v-else class="examples">
        <p v-if="library.stats" class="note">팀 라이브러리 논문 {{ library.stats.indexed }}편에서 근거를 찾아 답해요.</p>
        <div class="chips">
          <button v-for="ex in EXAMPLES" :key="ex" type="button" class="chip" @click="question = ex; input.focus()">{{ ex }}</button>
        </div>
      </div>
      <ul v-if="facts.length && !library.isEmpty" class="facts">
        <li v-for="f in facts" :key="f.text" class="fact" :class="f.tone" >
          <span class="fact-big">{{ f.big }}</span>
          <span class="fact-text">{{ f.text }}</span>
        </li>
      </ul>
    </div>

    <TopicSearchModal :open="topicOpen" :initial-query="trimmed" @close="topicOpen = false" @done="library.refresh()" />
  </div>
</template>

<style scoped>
.home {
  min-height: calc(100vh - 52px);
  display: grid;
  place-items: center;
  padding: 48px 24px 96px;
}

.center {
  width: 100%;
  max-width: 760px;
  display: grid;
  justify-items: center;
  gap: 28px;
  text-align: center;
}

/* 가는 테두리 숫자 카드 */
.facts {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  width: 100%;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.fact {
  padding: 18px 12px;
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-m);
  background: var(--c-paper);
  color: var(--c-ink-muted);
  display: grid;
  gap: 4px;
}

.fact-big {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--c-ink);
}

.fact-text {
  font-size: var(--fs-xs);
}

/* 시안처럼 흰 알약 하나에 + · 입력 · 조건 · 마이크 · 보내기 */
.ask-pill {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 10px 10px 14px;
  border-radius: 999px;
  background: var(--c-paper);
  box-shadow: var(--shadow-float);
  text-align: left;
}

.ask-pill:focus-within {
  box-shadow: 0 0 0 2px var(--c-accent-2), var(--shadow-float);
}

.plus {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  list-style: none;
}

.plus::-webkit-details-marker,
.cond::-webkit-details-marker {
  display: none;
}

.q-input {
  flex: 1;
  min-width: 0;
  max-height: 160px;
  padding: 8px 6px;
  border: 0;
  background: none;
  font-size: var(--fs-lg);
  line-height: 1.5;
  resize: none;
  field-sizing: content; /* 쓴 만큼 줄이 늘어난다(지원하는 브라우저에서) */
}

.q-input:focus-visible {
  outline: none;
}

.q-input::placeholder {
  color: var(--c-ink-muted);
}

.menu-wrap {
  position: relative;
}

.cond {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 10px 0 12px;
  border-radius: 999px;
  font-size: var(--fs-md);
  list-style: none;
  cursor: pointer;
  white-space: nowrap;
}

.cond:hover {
  background: var(--c-surface);
}

.cond-view {
  font-weight: 500;
}

/* 작은 메뉴: 알약 아래로 펼친다 */
.pop {
  position: absolute;
  top: calc(100% + 10px);
  left: 0;
  z-index: 10;
  min-width: 220px;
  padding: 8px;
  border-radius: var(--radius-l);
  background: var(--c-paper);
  box-shadow: var(--shadow-float);
  display: grid;
  gap: 2px;
}

.pop a,
.pop button {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 0;
  border-radius: var(--radius-m);
  background: none;
  color: var(--c-ink);
  font-size: var(--fs-sm);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

.pop a:hover,
.pop button:hover {
  background: var(--c-surface);
}

.cond-pop {
  left: auto;
  right: 0;
  width: 300px;
  padding: 16px;
}

/* 관점 고르기 안의 버튼은 메뉴 항목 모양을 따르지 않는다 */
.cond-pop :deep(.segmented button) {
  display: inline-flex;
  padding: 0 12px;
  border-radius: 999px;
}

.cond-pop :deep(.segmented button[aria-pressed="true"]) {
  background: var(--c-black);
  color: var(--c-on-black);
}

.send {
  flex: none;
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: var(--c-accent);
  color: var(--c-on-accent);
  cursor: pointer;
}

.send:disabled {
  background: var(--c-surface);
  color: var(--c-ink-muted);
  cursor: default;
}

.note {
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}

.link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--c-accent);
  font-size: inherit;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

.examples {
  display: grid;
  justify-items: center;
  gap: 12px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.chip {
  padding: 7px 14px;
  border: 1px solid var(--c-glass-line);
  border-radius: 999px;
  background: var(--c-glass);
  color: var(--c-text);
  font-size: var(--fs-sm);
  cursor: pointer;
}

.chip:hover {
  background: var(--c-paper);
}

@media (max-width: 640px) {
  .facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }


  .home {
    place-items: start center;
    padding-top: 18vh;
  }

  .ask-pill {
    flex-wrap: wrap;
    border-radius: 24px;
  }

  .q-input {
    order: -1;
    flex-basis: 100%;
    padding: 8px 6px 4px;
  }

  .cond-pop {
    right: auto;
    left: 0;
    width: min(300px, 80vw);
  }

  .menu-wrap:has(.cond) {
    margin-left: auto;
  }
}
</style>
