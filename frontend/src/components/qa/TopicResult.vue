<script setup>
import { computed } from 'vue'
import Icon from '@/components/common/Icon.vue'
import SourceList from './SourceList.vue'
import TopicCards from './TopicCards.vue'
import CiteChip from './CiteChip.vue'

// 주제 모드 결과: 찾은 한계(접이식) → 주제 후보 카드 → 고지 → 근거 목록
const props = defineProps({
  result: { type: Object, required: true }, // { limitations, topics, sources, source_details, needs_review, handoff }
  params: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
  active: { type: Object, default: null },
})
// 쓰지 않는 이벤트도 선언해 두어 화면 요소로 새어 나가지 않게 한다
const emit = defineEmits(['cite', 'pick-papers', 'reask', 'add-paper', 'ask-team', 'research'])

const details = computed(() => props.result.source_details ?? [])
const topics = computed(() => props.result.topics ?? [])
const limitations = computed(() => props.result.limitations ?? [])
const isHandoff = computed(() => props.result.handoff || !topics.value.length)
</script>

<template>
  <div v-if="isHandoff" class="callout info" role="status">
    <Icon name="forward" />
    <div>
      <p class="callout-title">주제를 제안할 근거를 찾지 못했어요</p>
      <p class="text">고른 논문에서 한계를 서술한 부분을 찾지 못했어요. 다른 논문을 고르거나 논문을 더 추가해 보세요.</p>
      <button type="button" class="btn btn-primary" @click="emit('pick-papers')">다른 논문 선택하기</button>
    </div>
  </div>
  <div v-else class="topic-result">
    <details v-if="limitations.length" class="limits">
      <summary>찾은 한계 {{ limitations.length }}건</summary>
      <ul>
        <li v-for="l in limitations" :key="l.label">
          <CiteChip :label="l.label" @cite="emit('cite', $event)" />
          <span class="where">{{ l.title }}<template v-if="l.page"> {{ l.page }}쪽</template></span>
          <span class="sum">{{ l.summary }}</span>
        </li>
      </ul>
    </details>
    <TopicCards :topics="topics" @cite="emit('cite', $event)" />
    <p class="notice hint">AI가 제안한 후보예요. 라이브러리 밖의 신규성은 보증하지 않아요. 쓰기 전에 직접 확인하세요.</p>
    <SourceList :items="details" :fallback="result.sources ?? []" :active="active" :needs-review="!!result.needs_review" />
  </div>
</template>

<style scoped>
.topic-result {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.limits {
  padding: 10px 14px;
  border: 1px solid var(--c-rule);
  border-radius: var(--radius-m);
  font-size: var(--fs-sm);
}

.limits summary {
  cursor: pointer;
  font-weight: 600;
}

.limits ul {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.limits li {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  align-items: baseline;
}

.where {
  font-weight: 600;
}

.sum {
  flex-basis: 100%;
  color: var(--c-ink-muted);
}
</style>
