<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api/client'
import { errorText } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { useLibraryStore } from '@/stores/library'
import { toast } from '@/composables/useToast'
import { PAPER_STATUS, SOURCE_TYPE } from '@/lib/format'
import PaperTable from '@/components/library/PaperTable.vue'
import UploadDropzone from '@/components/library/UploadDropzone.vue'
import TopicSearchModal from '@/components/library/TopicSearchModal.vue'
import ZoteroPanel from '@/components/library/ZoteroPanel.vue'
import StatusBanner from '@/components/common/StatusBanner.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'

const PAGE_SIZE = 20

const auth = useAuthStore()
const library = useLibraryStore()
const route = useRoute()
const router = useRouter()

const filters = reactive({ q: '', source_type: '', tag: '', status: '' })
const page = ref(1)
const list = ref({ items: [], total: 0 })
const loading = ref(false)
const error = ref(null)

// 홈의 + → "PDF 올리기"로 오면 올리기 칸을 펼친 채로 연다
const uploadOpen = ref(Boolean(route.query.upload))
// Q&A의 "논문 추가하기"로 오면 질문을 검색어로 미리 채워 주제 수집 창을 연다
const topicQuery = ref(String(route.query.topic ?? ''))
const topicOpen = ref(Boolean(route.query.topic))

const pendingDelete = ref(null)
const deleting = ref(false)

let requestSeq = 0
async function load() {
  const mine = ++requestSeq
  loading.value = true
  error.value = null
  try {
    const data = await api.rag('/papers', { query: { ...filters, page: page.value, size: PAGE_SIZE } })
    if (mine === requestSeq) list.value = data ?? { items: [], total: 0 }
  } catch (e) {
    if (mine === requestSeq) error.value = e
  } finally {
    if (mine === requestSeq) loading.value = false
  }
}

function refreshAll() {
  return Promise.all([load(), library.refresh()]) // 둘 다 실패해도 던지지 않는다(load는 error에 담고 refresh는 allSettled)
}

let debounce
watch(
  () => filters.q,
  () => {
    clearTimeout(debounce)
    debounce = setTimeout(() => {
      page.value = 1
      load()
    }, 300)
  },
)
watch(
  () => [filters.source_type, filters.tag, filters.status],
  () => {
    page.value = 1
    load()
  },
)
watch(page, load)

onMounted(refreshAll)

const filtering = computed(() => Boolean(filters.q || filters.source_type || filters.tag || filters.status))
const lastPage = computed(() => Math.max(1, Math.ceil((list.value.total ?? 0) / PAGE_SIZE)))
const rangeText = computed(() => {
  const total = list.value.total ?? 0
  if (!total) return '0건'
  const from = (page.value - 1) * PAGE_SIZE + 1
  return `${from}–${Math.min(page.value * PAGE_SIZE, total)} / ${total}건`
})

const summary = computed(() => {
  const s = library.stats
  if (!s) return ''
  const failed = s.failed ? `, 실패 ${s.failed}편` : ''
  return `논문 ${s.papers}편 중 ${s.indexed}편 색인 완료${failed}`
})

// 삭제는 팀 관리자 또는 등록한 사람만 (기능명세서 2.6). added_by가 응답에 없으면 관리자만 보인다.
const canDelete = (paper) => auth.isAdmin || (paper.added_by != null && String(paper.added_by) === String(auth.claims?.sub))

async function confirmDelete() {
  const paper = pendingDelete.value
  if (!paper) return
  deleting.value = true
  try {
    await api.rag(`/papers/${encodeURIComponent(paper.id)}`, { method: 'DELETE' })
    await refreshAll() // 목록에서 사라진 뒤에 알린다
    toast('논문을 삭제했어요. Zotero 휴지통에서 복구할 수 있어요.')
    pendingDelete.value = null
  } catch (e) {
    toast(errorText(e), { tone: 'error' })
  } finally {
    deleting.value = false
  }
}

function openTopic() {
  topicQuery.value = ''
  topicOpen.value = true
}

function closeTopic() {
  topicOpen.value = false
  if (route.query.topic) router.replace({ query: {} })
}

function openPaper(paper) {
  router.push({ name: 'paper', params: { id: paper.id } })
}
</script>

<template>
  <section class="library">
    <header class="head">
      <div>
        <h1>팀 라이브러리</h1>
        <p class="summary">
          <template v-if="summary">{{ summary }}.</template>
        </p>
      </div>
      <div class="add">
        <button type="button" class="btn" :aria-expanded="uploadOpen" @click="uploadOpen = !uploadOpen">PDF 올리기</button>
        <button type="button" class="btn btn-primary" @click="openTopic">주제로 찾기</button>
      </div>
    </header>

    <UploadDropzone v-if="uploadOpen" class="block" @done="refreshAll" />
    <ZoteroPanel class="block zotero" :is-admin="auth.isAdmin" :last-synced-at="library.stats?.last_synced_at ?? null" @done="refreshAll" />

    <!-- 검색과 필터를 표 바로 위 한 줄에 모은다 -->
    <div class="toolbar" role="search">
      <label class="visually-hidden" for="lib-q">검색</label>
      <input id="lib-q" v-model="filters.q" class="input search" type="search" placeholder="제목으로 찾기" />
      <label class="visually-hidden" for="lib-source">출처</label>
      <select id="lib-source" v-model="filters.source_type" class="input" :class="{ set: filters.source_type }">
        <option value="">출처 전체</option>
        <option v-for="(name, key) in SOURCE_TYPE" :key="key" :value="key">{{ name }}</option>
      </select>
      <label class="visually-hidden" for="lib-tag">태그</label>
      <select id="lib-tag" v-model="filters.tag" class="input" :class="{ set: filters.tag }">
        <option value="">태그 전체</option>
        <option v-for="t in library.tags" :key="t" :value="t">{{ t }}</option>
      </select>
      <label class="visually-hidden" for="lib-status">상태</label>
      <select id="lib-status" v-model="filters.status" class="input" :class="{ set: filters.status }">
        <option value="">상태 전체</option>
        <option v-for="(name, key) in PAPER_STATUS" :key="key" :value="key">{{ name }}</option>
      </select>
      <span class="hint tabular count">{{ rangeText }}</span>
    </div>

    <StatusBanner v-if="error" :message="error.message" :retry="error.retryable" @retry="load" />
    <div v-else-if="loading && !list.items.length" class="skeleton block" aria-label="목록을 불러오는 중"><span></span><span></span><span></span></div>
    <EmptyState v-else-if="!list.items.length && !filtering" title="팀 라이브러리가 비어 있어요" text="PDF를 올리거나 주제로 논문을 찾아 추가하세요. 추가한 논문은 색인이 끝나면 질문에 쓰여요.">
      <button type="button" class="btn btn-primary" @click="openTopic">주제로 찾기</button>
      <button type="button" class="btn" @click="uploadOpen = true">PDF 올리기</button>
    </EmptyState>
    <p v-else-if="!list.items.length" class="none">조건에 맞는 논문이 없어요. 검색어나 필터를 바꿔 보세요.</p>
    <template v-else>
      <div class="table-frame">
        <PaperTable :items="list.items" :can-delete="canDelete" :class="{ dim: loading }" @open="openPaper" @delete="pendingDelete = $event" />
      </div>
      <nav v-if="lastPage > 1" class="pager" aria-label="페이지">
        <button type="button" class="btn" :disabled="page <= 1 || loading" @click="page--">이전</button>
        <button type="button" class="btn" :disabled="page >= lastPage || loading" @click="page++">다음</button>
      </nav>
    </template>

    <TopicSearchModal :open="topicOpen" :initial-query="topicQuery" @close="closeTopic" @done="refreshAll" />
    <ConfirmDialog
      :open="Boolean(pendingDelete)"
      title="논문을 삭제할까요?"
      :message="pendingDelete ? `'${pendingDelete.title}'을(를) Zotero 휴지통으로 옮기고 색인된 청크를 지워요. Zotero에서 복구할 수 있어요.` : ''"
      confirm-label="삭제"
      danger
      :busy="deleting"
      @confirm="confirmDelete"
      @cancel="pendingDelete = null"
    />
  </section>
</template>

<style scoped>
.library {
  padding-bottom: 48px;
}

.head {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 16px;
}

h1 {
  font-size: var(--fs-2xl);
}

.summary {
  margin-top: 6px;
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
}

.add {
  margin-left: auto;
  display: flex;
  gap: 8px;
}

.block {
  margin-top: 20px;
}

.zotero {
  margin-top: 12px;
}

.toolbar {
  margin: 28px 0 12px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.toolbar .input {
  width: auto;
  min-height: 34px;
  font-size: var(--fs-sm);
}

.toolbar .search {
  flex: 1 1 220px;
  max-width: 320px;
}

/* 고른 필터는 초록 테두리로 표시해 지금 무엇으로 좁혔는지 보이게 한다 */
.toolbar select.set {
  border-color: var(--c-accent);
  color: var(--c-accent);
}

.count {
  margin-left: auto;
}

.none {
  padding: 24px 0;
  color: var(--c-ink-muted);
}

.dim {
  opacity: 0.6;
}

.pager {
  margin-top: 16px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 720px) {
  .add {
    margin-left: 0;
  }
}
</style>
