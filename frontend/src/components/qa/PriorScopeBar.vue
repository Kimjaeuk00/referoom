<script setup>
import { computed } from 'vue'
import { useQaStore } from '@/stores/qa'

// 선행연구 모드의 조사 범위: 수집해 둔 논문 N편 / 라이브러리 / 아직 없음(보내면 논문을 먼저 찾는다)
const qa = useQaStore()
const text = computed(() => {
  if (qa.libraryOnly) return '라이브러리 안에서만 찾아요'
  if (qa.priorScope.length) return `조사 범위: 논문 ${qa.priorScope.length}편`
  return '보내면 논문을 먼저 찾아 모아요'
})
</script>

<template>
  <div class="scope-bar" role="group" aria-label="선행연구 조사 범위">
    <span class="scope-text">{{ text }}</span>
    <button v-if="qa.priorScope.length" type="button" class="btn-quiet" @click="qa.priorScope = []">범위 바꾸기</button>
    <label class="only"><input type="checkbox" v-model="qa.libraryOnly" /> 라이브러리 안에서만 찾기</label>
  </div>
</template>

<style scoped>
.scope-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 12px;
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}

.only {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
</style>
