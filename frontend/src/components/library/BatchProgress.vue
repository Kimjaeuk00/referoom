<script setup>
import { computed } from 'vue'
import { BATCH_ITEM_STATUS } from '@/lib/format'

// GET /ingest/batches/{id} 응답(DEV_03 5.1):
// { id, kind: upload_pdf|topic|zotero_sync, status: running|done|failed, requested, indexed, skipped, failed, removed, error_msg, papers: [{ paper_id, title, status, chunk_count, error_msg? }] }
// removed: 동기화로 색인에서 지운 논문 수, error_msg: 배치 전체가 실패한 이유(예: Zotero에 연결하지 못함)
const props = defineProps({ batch: { type: Object, required: true } })

const finished = computed(() => props.batch.indexed + props.batch.skipped + props.batch.failed)
const headline = computed(() => {
  const { status, requested, indexed, skipped, failed, removed } = props.batch
  if (status === 'running') return `색인하는 중이에요 (${finished.value}/${requested})`
  if (status === 'failed') return '색인하지 못했어요'
  const parts = [`${indexed}건 완료`, skipped && `${skipped}건 건너뜀`, failed && `${failed}건 실패`, removed && `${removed}건 색인에서 제거`].filter(Boolean)
  return `색인을 마쳤어요. ${parts.join(', ')}`
})
</script>

<template>
  <div class="batch" :class="batch.status">
    <div class="head">
      <p role="status">{{ headline }}</p>
      <progress :max="batch.requested || 1" :value="finished" :aria-label="headline" />
    </div>
    <p v-if="batch.error_msg" class="reason" role="alert">{{ batch.error_msg }}</p>
    <ul v-if="batch.papers?.length" class="items">
      <li v-for="item in batch.papers" :key="item.paper_id ?? item.title">
        <span class="status" :class="item.status">{{ BATCH_ITEM_STATUS[item.status] ?? item.status }}</span>
        <span class="title">{{ item.title }}</span>
        <span v-if="item.error_msg" class="reason">{{ item.error_msg }}</span>
      </li>
    </ul>
    <slot />
  </div>
</template>

<style scoped>
.batch {
  padding: 12px 14px;
  border: 1px solid var(--c-rule);
  border-radius: var(--radius-m);
  background: var(--c-surface);
  font-size: var(--fs-sm);
}

.head {
  display: grid;
  gap: 6px;
}

progress {
  width: 100%;
  height: 6px;
  accent-color: var(--c-accent);
}

.items {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
}

.items li {
  display: grid;
  grid-template-columns: 52px 1fr auto;
  gap: 8px;
  align-items: baseline;
}

.title {
  line-height: 1.4;
}

.reason {
  color: var(--c-danger);
  font-size: var(--fs-xs);
}
</style>
