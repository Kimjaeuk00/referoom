<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, TIMEOUT } from '@/api/client'
import { errorText } from '@/api/errors'
import { useProfileStore } from '@/stores/profile'
import { renderMarkdown } from '@/lib/markdown'
import { formatDate, PAPER_STATUS, SOURCE_TYPE, toneOfTag } from '@/lib/format'
import LevelViewSelector from '@/components/common/LevelViewSelector.vue'
import StatusBanner from '@/components/common/StatusBanner.vue'
import ReviewBadge from '@/components/qa/ReviewBadge.vue'
import PdfViewer from '@/components/paper/PdfViewer.vue'

const route = useRoute()
const profile = useProfileStore()

const paper = ref(null)
const loadError = ref(null)

const level = ref(profile.level)
const view = ref(profile.view)
const summary = ref(null)
const summarizing = ref(false)
const summaryError = ref(null)

const page = computed(() => Number(route.query.page) || null)

// Semantic Reader처럼 요약 섹션을 문제·방법·결과 세 갈래로 칠해 훑어보기 쉽게 한다.
// 섹션 key는 DEV_04 예시 기준이고, 모르는 key는 색 없이 둔다.
const KINDS = [
  { id: 'goal', name: '문제와 목표' },
  { id: 'method', name: '방법' },
  { id: 'result', name: '결과' },
]
const KIND_OF = { problem: 'goal', idea: 'goal', method: 'method', check: 'method', result: 'result' }
const lit = ref(new Set(KINDS.map((k) => k.id)))
const kindCount = (id) => summary.value?.sections.filter((s) => KIND_OF[s.key] === id).length ?? 0

function toggleKind(id) {
  const next = new Set(lit.value)
  next.has(id) ? next.delete(id) : next.add(id)
  lit.value = next
}

// "제목 p.4" → { title, page }
function parseSource(text) {
  const m = /^(.*)\s+p\.(\d+)$/.exec(text)
  return m ? { title: m[1], page: Number(m[2]) } : { title: text, page: null }
}

function jumpTo(key) {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(`sec-${key}`)?.scrollIntoView({ block: 'start', behavior: reduce ? 'auto' : 'smooth' })
}

// 원문 칸: 출처(?page=)를 따라 들어오면 그 쪽을 바로 연다
const viewer = ref(null)
function openPdf(atPage) {
  viewer.value = { id: paper.value.id, title: paper.value.title, url: paper.value.url, page: atPage || 1 }
}

async function load(id) {
  paper.value = null
  loadError.value = null
  summary.value = null
  viewer.value = null
  try {
    paper.value = await api.rag(`/papers/${encodeURIComponent(id)}`)
    if (page.value) openPdf(page.value)
  } catch (e) {
    loadError.value = e
  }
}

watch(() => route.params.id, load, { immediate: true })

async function summarize() {
  if (summarizing.value) return
  summarizing.value = true
  summaryError.value = null
  try {
    summary.value = await api.rag('/summary', {
      method: 'POST',
      json: { paper_id: paper.value.id, level: level.value, view: view.value },
      timeout: TIMEOUT.query,
    })
  } catch (e) {
    summaryError.value = e
  } finally {
    summarizing.value = false
  }
}
</script>

<template>
  <div class="paper" :class="{ reading: viewer }">
    <!-- 원문을 열면 왼쪽은 원문, 오른쪽은 요약 -->
    <div v-if="viewer" class="reader-col">
      <PdfViewer :paper="viewer" :show-detail-link="false" @close="viewer = null" />
    </div>
    <StatusBanner v-if="loadError" :message="errorText(loadError, { NOT_FOUND: '이 논문을 찾을 수 없어요. 삭제됐을 수 있어요.' })" />
    <div v-else-if="!paper" class="skeleton" aria-label="불러오는 중"><span></span><span></span><span></span></div>

    <template v-else>
      <article class="reader">
        <RouterLink to="/library" class="back">팀 라이브러리</RouterLink>
        <header class="head">
          <h1>{{ paper.title }}</h1>
          <p class="byline">{{ [paper.authors, paper.year].filter(Boolean).join(', ') }}</p>
          <div class="links">
            <RouterLink class="btn btn-primary" :to="{ name: 'ask', query: { paper: paper.id, title: paper.title } }">이 논문에 질문하기</RouterLink>
            <button type="button" class="btn" @click="openPdf(page)">원문 보기</button>
          </div>
        </header>

        <p v-if="page" class="page-note">
          답변의 근거는 이 논문의 <strong>{{ page }}쪽</strong>이에요.
          <button type="button" class="btn-quiet page-open" @click="openPdf(page)">{{ page }}쪽 원문 보기</button>
        </p>

        <section class="summary" aria-labelledby="summary-title">
          <h2 id="summary-title">구조 요약</h2>
          <p class="hint">이 논문 안에서만 찾아 섹션별로 정리하고, 섹션마다 근거 쪽수를 붙여요.</p>
          <div class="summary-controls">
            <LevelViewSelector v-model:level="level" v-model:view="view" :disabled="summarizing" />
            <button type="button" class="btn btn-primary" :disabled="summarizing || paper.status !== 'indexed'" @click="summarize">
              {{ summarizing ? '요약을 만드는 중' : summary ? '이 조건으로 다시 요약' : '구조 요약 보기' }}
            </button>
          </div>
          <p v-if="paper.status !== 'indexed'" class="hint">색인이 끝난 논문만 요약할 수 있어요.</p>
          <div v-if="summarizing" class="skeleton" aria-label="요약을 만드는 중"><span></span><span></span><span></span></div>
          <StatusBanner v-if="summaryError" :message="summaryError.message" :retry="summaryError.retryable" @retry="summarize" />

          <!-- POST /summary 응답(DEV_04 3.1): sections[{ key, title, text, sources: ["제목 p.4"] }], needs_review -->
          <template v-if="summary && !summarizing">
            <div class="kinds" role="group" aria-label="강조할 내용">
              <span class="hint">강조</span>
              <button
                v-for="k in KINDS"
                :key="k.id"
                type="button"
                class="kind-toggle"
                :class="k.id"
                :aria-pressed="lit.has(k.id)"
                :disabled="!kindCount(k.id)"
                @click="toggleKind(k.id)"
              >
                {{ k.name }} <span class="tabular">{{ kindCount(k.id) }}</span>
              </button>
            </div>
            <ReviewBadge v-if="summary.needs_review" />

            <section
              v-for="s in summary.sections"
              :id="`sec-${s.key}`"
              :key="s.key"
              class="section"
              :class="[KIND_OF[s.key], { lit: lit.has(KIND_OF[s.key]) }]"
            >
              <h3>{{ s.title }}</h3>
              <div class="prose" v-html="renderMarkdown(s.text)" />
              <div v-if="s.sources?.length" class="cites">
                <details v-for="src in s.sources.map(parseSource)" :key="`${src.title}-${src.page}`" class="cite-card">
                  <summary>근거 {{ src.page ? `${src.page}쪽` : '보기' }}</summary>
                  <div class="card">
                    <p class="card-title">{{ src.title }}</p>
                    <p class="hint">
                      <template v-if="src.page">{{ src.page }}쪽에서 가져온 내용이에요.</template>
                      원문에서 앞뒤 맥락을 확인하세요.
                    </p>
                    <button type="button" class="btn-quiet card-open" @click="openPdf(src.page)">{{ src.page ? `${src.page}쪽 원문 보기` : '원문 보기' }}</button>
                  </div>
                </details>
              </div>
            </section>
          </template>
        </section>
      </article>

      <aside class="rail" aria-label="논문 정보">
        <dl class="facts">
          <div><dt>출처</dt><dd>{{ SOURCE_TYPE[paper.source_type] ?? paper.source_type }}</dd></div>
          <div>
            <dt>상태</dt>
            <dd>
              <span class="status" :class="paper.status">{{ PAPER_STATUS[paper.status] ?? paper.status }}</span>
              <span v-if="paper.error_msg" class="reason">{{ paper.error_msg }}</span>
            </dd>
          </div>
          <div v-if="paper.chunk_count != null"><dt>청크</dt><dd class="tabular">{{ paper.chunk_count }}개</dd></div>
          <div v-if="paper.doi"><dt>DOI</dt><dd>{{ paper.doi }}</dd></div>
          <div><dt>등록일</dt><dd class="tabular">{{ formatDate(paper.created_at) }}</dd></div>
          <div v-if="paper.tags?.length"><dt>태그</dt><dd><span v-for="t in paper.tags" :key="t" class="tag" :class="toneOfTag(t)">{{ t }}</span></dd></div>
        </dl>

        <nav v-if="summary && !summarizing" class="toc" aria-label="요약 목차">
          <p class="toc-title">요약 목차</p>
          <button v-for="s in summary.sections" :key="s.key" type="button" :class="KIND_OF[s.key]" @click="jumpTo(s.key)">{{ s.title }}</button>
        </nav>
      </aside>
    </template>
  </div>
</template>

<style scoped>
.paper {
  display: grid;
  grid-template-columns: minmax(0, 720px) 240px;
  justify-content: space-between;
  gap: 56px;
  padding-bottom: 64px;
}

/* 원문 보는 중: 원문 | 요약, 정보 기둥은 숨긴다 */
.paper.reading {
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  gap: 32px;
}

.reading .rail {
  display: none;
}

.reader-col {
  position: sticky;
  top: 72px;
  align-self: start;
  height: calc(100vh - 92px);
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-m);
  overflow: hidden;
}

.back {
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
  text-decoration: none;
}

.back:hover {
  color: var(--c-accent);
  text-decoration: underline;
}

.head {
  margin-top: 12px;
}

h1 {
  font-size: var(--fs-2xl);
}

.byline {
  margin-top: 8px;
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
}

.links {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.links .btn {
  text-decoration: none;
}

.page-open,
.card-open {
  min-height: 0;
  padding: 0;
  font-weight: 600;
}

.page-note {
  margin-top: 24px;
  padding: 10px 14px;
  border-left: 3px solid var(--c-marker);
  background: var(--c-marker-soft);
  font-size: var(--fs-sm);
}

.summary {
  margin-top: 40px;
  padding-top: 28px;
  border-top: 1px solid var(--c-rule);
  display: grid;
  gap: 14px;
}

h2 {
  font-size: var(--fs-xl);
}

.summary-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 20px;
}

/* 강조 켜고 끄기: 색 견본 + 이름 + 섹션 수 */
.kinds {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.kinds .hint {
  margin-right: 4px;
}

.kind-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--c-rule-strong);
  border-radius: 999px;
  background: var(--c-paper);
  font-size: var(--fs-xs);
  cursor: pointer;
}

.kind-toggle::before {
  content: "";
  width: 10px;
  height: 10px;
  border-radius: 2px;
  border: 1.5px solid var(--kind);
}

.kind-toggle[aria-pressed="true"] {
  border-color: var(--kind);
  background: var(--kind-wash);
  color: var(--kind);
  font-weight: 500;
}

.kind-toggle[aria-pressed="true"]::before {
  background: var(--kind);
}

.kind-toggle:disabled {
  opacity: 0.4;
  cursor: default;
}

.goal {
  --kind: var(--c-goal);
  --kind-wash: var(--c-goal-wash);
}

.method {
  --kind: var(--c-method);
  --kind-wash: var(--c-method-wash);
}

.result {
  --kind: var(--c-result);
  --kind-wash: var(--c-result-wash);
}

/* 섹션: 왼쪽 선은 항상, 바탕색은 강조를 켰을 때만 */
.section {
  scroll-margin-top: 72px;
  padding: 14px 16px;
  border-left: 3px solid var(--kind, var(--c-rule));
  border-radius: 0 var(--radius-m) var(--radius-m) 0;
  transition: background-color 0.2s ease;
}

.section.lit {
  background: var(--kind-wash);
}

.section h3 {
  font-size: var(--fs-md);
  margin-bottom: 6px;
}

.section.lit h3 {
  color: var(--kind);
}

.prose {
  max-width: 68ch;
  line-height: 1.75;
}

.prose :deep(ul),
.prose :deep(ol) {
  margin: 0;
  padding-left: 1.3em;
}

/* 근거 카드: 누르면 그 자리에 펼쳐진다 */
.cites {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cite-card summary {
  display: inline-block;
  padding: 0 6px;
  border-radius: 2px;
  background: linear-gradient(transparent 18%, var(--c-marker) 18%, var(--c-marker) 86%, transparent 86%);
  font-size: var(--fs-xs);
  font-weight: 600;
  list-style: none;
  cursor: pointer;
}

.cite-card summary::-webkit-details-marker {
  display: none;
}

.cite-card[open] {
  flex-basis: 100%;
}

.card {
  margin-top: 8px;
  max-width: 460px;
  padding: 12px 14px;
  border: 1px solid var(--c-rule);
  border-radius: var(--radius-m);
  background: var(--c-paper);
  box-shadow: var(--shadow-card);
  display: grid;
  gap: 4px;
  font-size: var(--fs-sm);
}

.card-title {
  font-weight: 500;
  line-height: 1.45;
}

/* 오른쪽 기둥: 논문 정보와 요약 목차 */
.rail {
  position: sticky;
  top: 84px;
  align-self: start;
  display: grid;
  gap: 28px;
  font-size: var(--fs-sm);
}

.facts {
  margin: 0;
  display: grid;
  gap: 12px;
}

.facts dt {
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.facts dd {
  margin: 2px 0 0;
}

.reason {
  display: block;
  margin-top: 2px;
  color: var(--c-danger);
  font-size: var(--fs-xs);
}

.toc {
  padding-top: 20px;
  border-top: 1px solid var(--c-rule);
  display: grid;
  gap: 2px;
}

.toc-title {
  margin-bottom: 6px;
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.toc button {
  padding: 4px 0 4px 10px;
  border: 0;
  border-left: 2px solid var(--kind, var(--c-rule));
  background: none;
  text-align: left;
  cursor: pointer;
}

.toc button:hover {
  color: var(--c-accent);
}

@media (max-width: 960px) {
  .paper {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .paper.reading {
    grid-template-columns: 1fr;
  }

  .reader-col {
    position: fixed;
    inset: 52px 0 0;
    z-index: 30;
    height: auto;
    border: 0;
    border-radius: 0;
  }

  .rail {
    position: static;
  }

  .toc {
    display: none;
  }

  .facts {
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  }
}
</style>
