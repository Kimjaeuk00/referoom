<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '@/api/client'
import { errorText } from '@/api/errors'
import { usePolling } from '@/composables/usePolling'
import { formatDateTime, isBatchDone } from '@/lib/format'
import BatchProgress from './BatchProgress.vue'

// 동기화 시각은 /library/stats의 last_synced_at으로 모두가 본다.
// GET /zotero/config·POST /zotero/sync는 관리자 전용이라 팀원 화면에서는 부르지 않는다(DEV_03 5.1).
const props = defineProps({
  isAdmin: { type: Boolean, default: false },
  lastSyncedAt: { type: String, default: null },
})
const emit = defineEmits(['done'])

const config = ref(null)
const error = ref('')
const starting = ref(false)
const batchId = ref(null)

// GET /zotero/config → { configured, group_id, last_synced_at }. 연결되지 않았으면 group_id가 null이다
const connected = computed(() => config.value?.group_id != null)

const { data: batch, running: polling, error: pollError, start } = usePolling(
  () => api.rag(`/ingest/batches/${batchId.value}`),
  { isDone: isBatchDone },
)

watch(polling, (now, before) => {
  if (before && !now) emit('done', batch.value)
})

async function loadConfig() {
  try {
    config.value = await api.rag('/zotero/config')
  } catch (e) {
    error.value = errorText(e)
  }
}

async function sync() {
  if (starting.value || polling.value) return
  starting.value = true
  error.value = ''
  try {
    const data = await api.rag('/zotero/sync', { method: 'POST' })
    batchId.value = data.batch_id
    start()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    starting.value = false
  }
}

watch(() => props.isAdmin, (admin) => admin && loadConfig(), { immediate: true })
</script>

<template>
  <section class="zotero" aria-labelledby="zotero-title">
    <div class="row">
      <p id="zotero-title" class="name">Zotero</p>
      <template v-if="props.isAdmin">
        <p v-if="!config && !error" class="hint">연결 상태를 확인하는 중이에요.</p>
        <p v-else-if="config && !connected" class="state">
          연결되지 않았어요. <span class="hint">서버 설정(.env)에 Zotero 그룹이 필요해요.</span>
        </p>
        <p v-else-if="config" class="state">
          그룹 {{ config.group_id }}에 연결됨
          <span class="hint">마지막 동기화 {{ formatDateTime(props.lastSyncedAt ?? config.last_synced_at) }}</span>
        </p>
        <button v-if="connected" type="button" class="btn sync" :disabled="starting || polling" @click="sync">
          {{ polling ? '동기화하는 중' : '지금 동기화' }}
        </button>
      </template>
      <p v-else class="state">
        <template v-if="props.lastSyncedAt">마지막 동기화 {{ formatDateTime(props.lastSyncedAt) }}</template>
        <template v-else>동기화 기록이 없어요.</template>
        <span class="hint">동기화는 팀 관리자가 해요.</span>
      </p>
    </div>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    <p v-if="pollError" class="field-error" role="alert">{{ errorText(pollError) }}</p>
    <BatchProgress v-if="batch" :batch="batch" />
  </section>
</template>

<style scoped>
.zotero {
  display: grid;
  gap: 10px;
}

.row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  font-size: var(--fs-sm);
}

.name {
  font-weight: 600;
}

.state .hint {
  margin-left: 6px;
}

.sync {
  margin-left: auto;
}
</style>
