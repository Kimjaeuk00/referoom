<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, TIMEOUT } from '@/api/client'
import { errorText } from '@/api/errors'
import { usePolling } from '@/composables/usePolling'
import { useAuthStore } from '@/stores/auth'
import { isBatchDone } from '@/lib/format'
import BatchProgress from './BatchProgress.vue'

// 주제 수집(후보 선택 방식): 키워드 → POST /search-topic → 고른 논문만 POST /upload-topic → 배치 폴링 (DEV_02 4.3, DEV_03 5.1)
const props = defineProps({
  open: { type: Boolean, default: false },
  initialQuery: { type: String, default: '' },
})
const emit = defineEmits(['close', 'done'])
const MAX_PICK = 5
const auth = useAuthStore()

const dialog = ref(null)
const query = ref('')
const searchedFor = ref('')
const candidates = ref(null) // null = 아직 검색 전
const selected = ref([])
const searching = ref(false)
const collecting = ref(false)
const error = ref('')
const batchId = ref(null)

const { data: batch, running: polling, error: pollError, start } = usePolling(
  () => api.rag(`/ingest/batches/${batchId.value}`),
  { isDone: isBatchDone },
)

watch(polling, (now, before) => {
  if (before && !now) emit('done', batch.value)
})

function syncOpen(open) {
  if (open) {
    if (!polling.value) reset(props.initialQuery)
    if (!dialog.value?.open) dialog.value?.showModal()
    if (props.initialQuery && candidates.value === null) search()
  } else if (dialog.value?.open) {
    dialog.value.close()
  }
}

watch(() => props.open, syncOpen)
// 처음부터 열린 채로 그려질 때(라이브러리?topic=...)
onMounted(() => props.open && syncOpen(true))

function reset(initial = '') {
  query.value = initial
  searchedFor.value = ''
  candidates.value = null
  selected.value = []
  error.value = ''
  batchId.value = null
  batch.value = null
  confirmRollback.value = false
}

async function search() {
  const q = query.value.trim()
  if (q.length < 2 || searching.value) {
    if (q.length < 2) error.value = '주제를 두 글자 이상 입력하세요.'
    return
  }
  searching.value = true
  error.value = ''
  selected.value = []
  try {
    const data = await api.rag('/search-topic', { method: 'POST', json: { topic: q, max_results: 10, provider: 'arxiv' }, timeout: TIMEOUT.query })
    candidates.value = data?.candidates ?? []
    searchedFor.value = q
  } catch (e) {
    error.value = errorText(e)
  } finally {
    searching.value = false
  }
}

const isPicked = (c) => selected.value.includes(c.candidate_id)
const full = computed(() => selected.value.length >= MAX_PICK)

function toggle(c) {
  if (c.already_in_library) return
  if (isPicked(c)) selected.value = selected.value.filter((id) => id !== c.candidate_id)
  else if (!full.value) selected.value = [...selected.value, c.candidate_id]
}

// 관리자는 방금 수집한 배치를 통째로 되돌릴 수 있다(DEV_03 5.1, P1). 지운 논문은 되살릴 수 없어서 한 번 더 묻는다.
const confirmRollback = ref(false)
const rollingBack = ref(false)
const canRollback = computed(() => auth.isAdmin && batch.value && ['done', 'failed'].includes(batch.value.status))

async function rollback() {
  rollingBack.value = true
  error.value = ''
  try {
    await api.rag(`/ingest/batches/${batchId.value}/rollback`, { method: 'POST' })
    batch.value = await api.rag(`/ingest/batches/${batchId.value}`)
    emit('done', batch.value)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    rollingBack.value = false
    confirmRollback.value = false
  }
}

async function collect() {
  if (!selected.value.length || collecting.value) return
  collecting.value = true
  error.value = ''
  try {
    const data = await api.rag('/upload-topic', {
      method: 'POST',
      json: { topic: searchedFor.value, selected: selected.value },
      timeout: TIMEOUT.upload,
    })
    batchId.value = data.batch_id
    start()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    collecting.value = false
  }
}
</script>

<template>
  <dialog ref="dialog" class="topic" aria-labelledby="topic-title" @cancel.prevent="emit('close')">
    <div class="inner">
      <header class="head">
        <h2 id="topic-title">주제로 논문 찾기</h2>
        <button type="button" class="btn-quiet close" @click="emit('close')">닫기</button>
      </header>
      <p class="hint">arXiv에서 후보를 먼저 보여 드려요. 고른 논문만 내려받아 색인해요. 한 번에 {{ MAX_PICK }}편까지 고를 수 있어요.</p>

      <form class="search" @submit.prevent="search">
        <label class="visually-hidden" for="topic-query">주제</label>
        <input id="topic-query" v-model="query" class="input" placeholder="예: LoRA fine-tuning" :disabled="polling" />
        <button class="btn btn-primary" type="submit" :disabled="searching || polling">{{ searching ? '찾는 중' : '후보 찾기' }}</button>
      </form>

      <p v-if="error" class="field-error" role="alert">{{ error }}</p>

      <BatchProgress v-if="batch" :batch="batch">
        <div v-if="canRollback" class="rollback">
          <template v-if="confirmRollback">
            <span>이번에 추가한 논문 {{ batch.indexed + batch.failed }}편과 청크를 지울까요? 되돌릴 수 없어요.</span>
            <button type="button" class="btn btn-danger" :disabled="rollingBack" @click="rollback">{{ rollingBack ? '되돌리는 중' : '수집 되돌리기' }}</button>
            <button type="button" class="btn" :disabled="rollingBack" @click="confirmRollback = false">취소</button>
          </template>
          <button v-else type="button" class="btn-quiet" @click="confirmRollback = true">이번 수집 되돌리기</button>
        </div>
      </BatchProgress>
      <p v-if="pollError" class="field-error" role="alert">{{ errorText(pollError) }}</p>

      <template v-if="candidates !== null && !batch">
        <p v-if="!candidates.length" class="none">'{{ searchedFor }}'로 찾은 논문이 없어요. 더 넓은 키워드나 영어 키워드로 다시 찾아보세요.</p>
        <ul v-else class="cands">
          <li v-for="c in candidates" :key="c.candidate_id" :class="{ picked: isPicked(c), owned: c.already_in_library }">
            <label class="cand">
              <input type="checkbox" :checked="isPicked(c)" :disabled="c.already_in_library || (!isPicked(c) && full)" @change="toggle(c)" />
              <span class="cand-body">
                <span class="cand-title">{{ c.title }}</span>
                <span class="hint">{{ c.authors?.join(', ') }}, {{ c.year }}</span>
                <span class="abstract">{{ c.abstract }}</span>
                <span class="meta">
                  <span class="rel">
                    관련도
                    <meter min="0" max="1" low="0.5" high="0.8" optimum="1" :value="c.relevance" />
                    <span class="tabular">{{ Math.round(c.relevance * 100) }}%</span>
                  </span>
                  <span v-if="c.low_relevance" class="warn">주제와 관련이 낮아요</span>
                  <span v-if="c.already_in_library" class="owned-note">이미 라이브러리에 있어요</span>
                </span>
              </span>
            </label>
          </li>
        </ul>
        <footer v-if="candidates.length" class="foot">
          <span class="hint tabular">{{ selected.length }} / {{ MAX_PICK }}편 선택</span>
          <button type="button" class="btn btn-primary" :disabled="!selected.length || collecting" @click="collect">
            {{ collecting ? '수집을 시작하는 중' : `${selected.length}편 수집` }}
          </button>
        </footer>
      </template>
    </div>
  </dialog>
</template>

<style scoped>
.topic {
  width: min(720px, calc(100vw - 32px));
}

.inner {
  padding: 24px;
  display: grid;
  gap: 14px;
}

.head {
  display: flex;
  align-items: center;
}

.head h2 {
  font-size: var(--fs-xl);
}

.close {
  margin-left: auto;
}

.search {
  display: flex;
  gap: 8px;
}

.none {
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
}

.cands {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 52vh;
  overflow-y: auto;
  border-top: 1px solid var(--c-rule);
}

.cands li {
  border-bottom: 1px solid var(--c-rule);
}

.cands li.picked {
  background: var(--c-accent-wash);
}

.cands li.owned {
  opacity: 0.65;
}

.cand {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
  padding: 12px 6px;
  cursor: pointer;
}

.cand input {
  margin-top: 5px;
  accent-color: var(--c-accent);
}

.cand-body {
  display: grid;
  gap: 2px;
}

.cand-title {
  font-weight: 600;
  line-height: 1.4;
}

.abstract {
  margin-top: 2px;
  font-size: var(--fs-sm);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  font-size: var(--fs-xs);
}

.rel {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--c-ink-muted);
}

meter {
  width: 72px;
  height: 6px;
}

.warn {
  color: var(--c-review);
  font-weight: 600;
}

.owned-note {
  color: var(--c-ink-muted);
}

.rollback {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
}
</style>
