<script setup>
import { computed } from 'vue'
import { useQaStore } from '@/stores/qa'
import Icon from '@/components/common/Icon.vue'

// 선행연구 모드의 조사 범위: 라이브러리 / 체크한 논문 N편 / 수집해 둔 논문 N편 / 아직 없음(보내면 논문을 먼저 찾는다)
const qa = useQaStore()
const emit = defineEmits(['collect'])
const text = computed(() => {
  if (qa.libraryOnly) return '라이브러리 안에서만 찾아요'
  if (qa.pickedIds.length) return `조사 범위: 체크한 논문 ${qa.pickedIds.length}편`
  if (qa.priorScope.length) return `조사 범위: 논문 ${qa.priorScope.length}편`
  return '보내면 논문을 먼저 찾아 모아요'
})
</script>

<template>
  <div class="scope-bar" role="group" aria-label="선행연구 조사 범위">
    <span class="scope-text">{{ text }}</span>
    <span class="search-options">
      <label class="only"><input type="checkbox" v-model="qa.libraryOnly" /> 라이브러리 안에서만 찾기</label>
      <button v-if="qa.pickedIds.length && !qa.libraryOnly" type="button" class="btn btn-line web-search" @click="emit('collect')">
        <Icon name="search" :size="16" />
        웹 검색
      </button>
      <button v-else-if="qa.priorScope.length && !qa.libraryOnly" type="button" class="btn-quiet" @click="qa.priorScope = []">범위 바꾸기</button>
    </span>
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

.search-options {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.web-search {
  min-height: 32px;
  padding: 5px 10px;
  font-size: inherit;
  white-space: nowrap;
}

.only {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
}
</style>
