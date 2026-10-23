<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { apiBlob, BASE_URL } from '@/api/client'
import { arxivPdfUrl, safeUrl } from '@/lib/format'
import Icon from '@/components/common/Icon.vue'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

// 원문 PDF 칸(pdf.js). 부모가 칸 크기를 정하고, 여기서는 그 안을 채운다.
// 원문 순서: ① GET /papers/{id}/pdf (Bearer, 백엔드에 추가 요청한 경로) ② arXiv 원문 ③ 못 띄우면 새 탭 링크
// 화면에 보이는 쪽(앞뒤 한 쪽 포함)만 그려서 긴 논문도 가볍게 연다. 논문은 쪽 크기가 같다고 보고 높이를 계산한다.
const props = defineProps({
  paper: { type: Object, required: true }, // { id, title, url, page }
  showDetailLink: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])

const GAP = 12
const ZOOMS = [0.6, 0.8, 1, 1.25, 1.5, 2]

const scroller = ref(null)
const loading = ref(false)
const failed = ref(false)
const total = ref(0)
const current = ref(1)
const cited = ref(null)
const zoomIdx = ref(2)
const boxWidth = ref(600)
const externalUrl = ref(null) // 새 탭으로 열 수 있는 주소(arXiv 등)

let doc = null
let pageRatio = 1.414
let baseWidth = 595
const canvases = new Map() // 쪽 번호 → { el, task, scale }

const scale = computed(() => (Math.max(boxWidth.value - 32, 200) / baseWidth) * ZOOMS[zoomIdx.value])
const pageW = computed(() => Math.floor(baseWidth * scale.value))
const pageH = computed(() => Math.floor(pageW.value * pageRatio))
const pageSlots = ref([])
const slotEls = new Map()
const setSlot = (n) => (el) => (el ? slotEls.set(n, el) : slotEls.delete(n))

function reset() {
  for (const c of canvases.values()) c.task?.cancel()
  canvases.clear()
  doc?.destroy()
  doc = null
  pageSlots.value = []
  total.value = 0
  failed.value = false
  externalUrl.value = null
}

async function open(paper) {
  reset()
  loading.value = true
  let source = null
  try {
    const blob = await apiBlob(BASE_URL.rag, `/papers/${encodeURIComponent(paper.id)}/pdf`, { skipAuthRedirect: true })
    source = { data: new Uint8Array(await blob.arrayBuffer()) }
  } catch {
    // 백엔드에 원문이 없으면 arXiv 원문으로
    const url = arxivPdfUrl(paper.url)
    if (url) source = { url }
    externalUrl.value = url
  }
  try {
    if (!source) throw new Error('no source')
    const loaded = await pdfjs.getDocument(source).promise
    if (props.paper?.id !== paper.id) return loaded.destroy() // 받는 사이 다른 논문을 골랐다
    doc = loaded
    const first = (await doc.getPage(1)).getViewport({ scale: 1 })
    baseWidth = first.width
    pageRatio = first.height / first.width
    total.value = doc.numPages
    pageSlots.value = Array.from({ length: doc.numPages }, (_, i) => i + 1)
    loading.value = false
    await nextTick()
    jumpTo(paper.page || 1, true)
  } catch {
    failed.value = true
    loading.value = false
  }
}

// n쪽의 위치: 위 여백 + (쪽 높이 + 간격) × (n-1)
const topOf = (n) => GAP + (n - 1) * (pageH.value + GAP)

function jumpTo(n, mark = false) {
  if (!total.value) return
  const page = Math.min(Math.max(1, n), total.value)
  scroller.value?.scrollTo({ top: topOf(page) - GAP, behavior: 'auto' })
  current.value = page
  if (mark) cited.value = page
  renderVisible()
}

async function renderPage(n) {
  const s = scale.value
  const have = canvases.get(n)
  if (!doc || (have && have.scale === s)) return
  have?.task?.cancel()
  const page = await doc.getPage(n)
  const viewport = page.getViewport({ scale: s })
  const dpr = window.devicePixelRatio || 1
  const el = document.createElement('canvas')
  el.width = Math.floor(viewport.width * dpr)
  el.height = Math.floor(viewport.height * dpr)
  const task = page.render({
    canvas: el,
    canvasContext: el.getContext('2d'),
    viewport,
    transform: dpr === 1 ? undefined : [dpr, 0, 0, dpr, 0, 0],
  })
  canvases.set(n, { el, task, scale: s })
  try {
    await task.promise
    slotEls.get(n)?.replaceChildren(el)
  } catch (e) {
    // 확대를 바꾸거나 닫으면 그리던 것을 취소한다
    if (e?.name !== 'RenderingCancelledException') console.warn('[pdf] render', n, e)
  }
}

// 스크롤마다 바로 그리지 않고 잠깐 모아서 그린다(창이 뒤에 있어도 동작하게 타이머를 쓴다)
let timer = 0
function renderVisible() {
  clearTimeout(timer)
  timer = setTimeout(() => {
    const box = scroller.value
    if (!box || !total.value) return
    const step = pageH.value + GAP
    const first = Math.max(1, Math.floor(box.scrollTop / step))
    const last = Math.min(total.value, Math.ceil((box.scrollTop + box.clientHeight) / step) + 1)
    current.value = Math.min(total.value, Math.floor((box.scrollTop + box.clientHeight / 3) / step) + 1)
    for (let n = first; n <= last; n++) renderPage(n)
  }, 40)
}

// 칸 너비가 바뀌면 쪽 폭을 맞춘다
let resizeObs = null
watch(scroller, (el) => {
  resizeObs?.disconnect()
  if (!el) return
  // 칸 너비가 움직이는 동안(열고 닫는 전환)은 매번 다시 그리지 않고, 멈춘 뒤 한 번 맞춘다
  let first = true
  let wait = 0
  resizeObs = new ResizeObserver(([entry]) => {
    clearTimeout(wait)
    const width = entry.contentRect.width
    if (first) {
      first = false
      boxWidth.value = width
    } else {
      wait = setTimeout(() => (boxWidth.value = width), 180)
    }
  })
  resizeObs.observe(el)
})

// 확대·폭이 바뀌면 보던 쪽을 유지한 채 다시 그린다
watch(scale, async () => {
  const keep = current.value
  for (const c of canvases.values()) c.task?.cancel()
  canvases.clear()
  await nextTick()
  jumpTo(keep)
})

watch(() => props.paper?.id, () => props.paper && open(props.paper), { immediate: true })
// 같은 논문에서 다른 출처를 누르면 쪽만 옮긴다
watch(() => props.paper?.page, (page) => doc && jumpTo(page || 1, true))

function onKey(event) {
  if (event.key === 'Escape') emit('close')
}
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  resizeObs?.disconnect()
  clearTimeout(timer)
  reset()
})
</script>

<template>
  <section class="viewer" aria-label="원문 PDF">
    <header class="head">
      <div class="title-wrap">
        <p class="title">{{ paper.title }}</p>
        <p v-if="paper.page" class="cited-note">근거 {{ paper.page }}쪽</p>
      </div>
      <RouterLink v-if="showDetailLink" class="btn btn-quiet" :to="{ name: 'paper', params: { id: paper.id }, query: paper.page ? { page: paper.page } : {} }">
        논문 상세
      </RouterLink>
      <a v-if="externalUrl" class="icon-btn" :href="externalUrl" target="_blank" rel="noopener noreferrer" title="새 탭에서 열기" aria-label="새 탭에서 열기">
        <Icon name="forward" :size="18" />
      </a>
      <button type="button" class="icon-btn" title="닫기" aria-label="원문 닫기" @click="emit('close')">
        <Icon name="plus" :size="20" class="x" />
      </button>
    </header>

    <div v-if="total" class="tools" role="toolbar" aria-label="원문 보기 도구">
      <button type="button" class="icon-btn" :disabled="current <= 1" aria-label="이전 쪽" @click="jumpTo(current - 1)"><Icon name="chevron" :size="18" class="left" /></button>
      <span class="tabular pos" aria-live="polite">{{ current }} / {{ total }}</span>
      <button type="button" class="icon-btn" :disabled="current >= total" aria-label="다음 쪽" @click="jumpTo(current + 1)"><Icon name="chevron" :size="18" class="right" /></button>
      <button v-if="paper.page" type="button" class="btn btn-quiet back" @click="jumpTo(paper.page, true)">근거 쪽으로</button>
      <span class="spacer" />
      <button type="button" class="icon-btn" :disabled="zoomIdx === 0" aria-label="축소" @click="zoomIdx--">−</button>
      <span class="tabular zoom">{{ Math.round(ZOOMS[zoomIdx] * 100) }}%</span>
      <button type="button" class="icon-btn" :disabled="zoomIdx === ZOOMS.length - 1" aria-label="확대" @click="zoomIdx++">+</button>
    </div>

    <div ref="scroller" class="pages" @scroll.passive="renderVisible">
      <p v-if="loading" class="state">원문을 불러오는 중이에요.</p>
      <div v-else-if="failed" class="state">
        <p>이 논문의 원문 파일을 불러오지 못했어요.</p>
        <a v-if="safeUrl(paper.url)" class="btn" :href="safeUrl(paper.url)" target="_blank" rel="noopener noreferrer">원문 열기</a>
      </div>
      <div
        v-for="n in pageSlots"
        :key="n"
        :ref="setSlot(n)"
        class="page"
        :class="{ cited: cited === n }"
        :style="{ width: `${pageW}px`, height: `${pageH}px` }"
        :aria-label="`${n}쪽`"
      />
    </div>
  </section>
</template>

<style scoped>
.viewer {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--c-paper);
}

.head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 10px 10px 16px;
  border-bottom: 1px solid var(--c-rule);
}

.title-wrap {
  flex: 1;
  min-width: 0;
}

.title {
  font-weight: 600;
  font-size: var(--fs-sm);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cited-note {
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.head .btn {
  text-decoration: none;
}

/* + 아이콘을 45도 돌려 × 로 쓴다 */
.x {
  transform: rotate(45deg);
}

.tools {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--c-rule);
  font-size: var(--fs-sm);
}

.tools .icon-btn {
  width: 32px;
  height: 32px;
  font-size: 1.1rem;
}

.left {
  transform: rotate(90deg);
}

.right {
  transform: rotate(-90deg);
}

.pos,
.zoom {
  min-width: 52px;
  text-align: center;
  color: var(--c-ink-muted);
}

.back {
  min-height: 30px;
  margin-left: 4px;
}

.spacer {
  flex: 1;
}

.pages {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  background: var(--c-surface);
}

.page {
  flex: none;
  background: #fff;
  box-shadow: 0 1px 3px rgb(0 0 0 / 0.12);
}

.page :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}

/* 근거 쪽은 테두리로 잠깐 표시 */
.page.cited {
  outline: 3px solid var(--c-accent-2);
  outline-offset: 2px;
}

.state {
  margin: auto;
  display: grid;
  justify-items: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
  color: var(--c-ink-muted);
}

.state .btn {
  text-decoration: none;
}
</style>
