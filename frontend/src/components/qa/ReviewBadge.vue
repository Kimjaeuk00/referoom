<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import Icon from '@/components/common/Icon.vue'

// needs_review 안내. 무엇을 어디서 확인하면 되는지 구체적으로 말하고, 그 쪽으로 바로 가는 버튼을 단다.
const props = defineProps({
  text: { type: String, default: '' }, // 답변 본문(수식·수치가 있는지 보려고)
  sources: { type: Array, default: () => [] }, // source_details
})

const kind = computed(() => {
  if (/\$[^$]+\$/.test(props.text)) return '수식'
  if (/\d+(\.\d+)?\s*(%|배|점|BLEU)/.test(props.text)) return '수치'
  return null
})

// 같은 논문·같은 쪽은 한 번만
const pages = computed(() => {
  const seen = new Map()
  for (const s of props.sources) {
    if (!s.paper_id || !s.page) continue
    const key = `${s.paper_id}-${s.page}`
    if (!seen.has(key)) seen.set(key, s)
  }
  return [...seen.values()]
})

const pageText = computed(() => pages.value.map((s) => `${s.page}쪽`).join(', '))
</script>

<template>
  <div class="callout warn" role="note">
    <Icon name="alert" />
    <div>
      <p class="callout-title">
        <template v-if="kind && pages.length">{{ kind === '수식' ? '수식이' : '수치가' }} 들어간 답이에요. {{ pageText }}의 원래 {{ kind === '수식' ? '식' : '값' }}과 한 번 대조해 보세요.</template>
        <template v-else-if="pages.length">근거가 약한 답이에요. {{ pageText }}에서 앞뒤 맥락을 확인해 보세요.</template>
        <template v-else>수식이나 수치가 있거나 근거가 약한 답이에요. 쓰기 전에 원문에서 확인하세요.</template>
      </p>
      <div v-if="pages.length" class="jumps">
        <RouterLink
          v-for="s in pages"
          :key="`${s.paper_id}-${s.page}`"
          class="btn"
          :to="{ name: 'paper', params: { id: s.paper_id }, query: { page: s.page } }"
        >
          {{ s.title }} {{ s.page }}쪽 보기
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.jumps {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.jumps .btn {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  text-decoration: none;
  font-size: var(--fs-xs);
  min-height: 30px;
}
</style>
