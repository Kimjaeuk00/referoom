<script setup>
import { computed } from 'vue'
import { priorTableToCsv, priorTableToMarkdown } from '@/lib/modes'
import { toast } from '@/composables/useToast'
import AnswerView from './AnswerView.vue'
import PriorTable from './PriorTable.vue'

// 선행연구 결과: 답변 본문(AnswerView) 아래 근거 목록 앞에 정리표를 끼운다. 정리표 내보내기는 Markdown 복사와 CSV 저장.
const props = defineProps({
  result: { type: Object, required: true },
  params: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  active: { type: Object, default: null },
})
const emit = defineEmits(['reask', 'add-paper', 'ask-team', 'cite', 'research'])

const rows = computed(() => props.result.table ?? [])
const isHandoff = computed(() => props.result.handoff)

async function copyMarkdown() {
  try {
    await navigator.clipboard.writeText(priorTableToMarkdown(rows.value))
    toast('정리표를 Markdown으로 복사했어요.')
  } catch {
    toast('복사하지 못했어요.', { tone: 'error' })
  }
}

function downloadCsv() {
  const url = URL.createObjectURL(new Blob([priorTableToCsv(rows.value, { bom: true })], { type: 'text/csv;charset=utf-8' }))
  const link = Object.assign(document.createElement('a'), { href: url, download: '선행연구_정리표.csv' })
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="prior-result">
    <AnswerView
      :result="result"
      :params="params"
      :busy="busy"
      :active="active"
      @reask="emit('reask', $event)"
      @add-paper="emit('add-paper')"
      @ask-team="emit('ask-team')"
      @cite="emit('cite', $event)"
    >
      <template v-if="rows.length && !isHandoff" #after-body>
        <section class="table-block" aria-label="정리표">
          <div class="table-head">
            <h3>정리표</h3>
            <div class="actions">
              <button type="button" class="btn" @click="copyMarkdown">Markdown 복사</button>
              <button type="button" class="btn" @click="downloadCsv">CSV 저장</button>
            </div>
          </div>
          <PriorTable :rows="rows" @cite="emit('cite', $event)" />
        </section>
      </template>
      <slot />
    </AnswerView>
    <button v-if="isHandoff" type="button" class="btn" :disabled="busy" @click="emit('research')">다른 검색어로 새로 찾기</button>
  </div>
</template>

<style scoped>
.prior-result {
  display: grid;
  gap: 12px;
  justify-items: start;
  min-width: 0;
  max-width: 100%;
}

.prior-result > :first-child {
  width: 100%;
}

.table-block {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.table-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.table-head h3 {
  font-size: var(--fs-md);
}

.actions {
  display: flex;
  gap: 8px;
}
</style>
