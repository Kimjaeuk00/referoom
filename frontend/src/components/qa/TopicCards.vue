<script setup>
import { RouterLink } from 'vue-router'
import { perspectiveOf } from '@/lib/modes'
import CiteChip from './CiteChip.vue'

// 연구 주제 후보 카드. 서버가 만든 문자열은 모두 텍스트 보간으로만 그린다(HTML로 해석하지 않는다).
defineProps({ topics: { type: Array, required: true } })
defineEmits(['cite'])

const list = (value) => (Array.isArray(value) ? value.filter(Boolean) : [])
</script>

<template>
  <ul class="cards">
    <li v-for="(t, i) in topics" :key="i" class="card">
      <div class="badges">
        <span class="badge persp">{{ perspectiveOf(t.perspective) }}</span>
        <span class="badge ai">AI 제안</span>
      </div>
      <h3>{{ t.title }}</h3>
      <dl>
        <div>
          <dt>연구 질문</dt>
          <dd>{{ t.question }}</dd>
        </div>
        <div>
          <dt>접근 아이디어</dt>
          <dd>{{ t.approach }}</dd>
        </div>
        <div v-if="t.experiment">
          <dt>검증 실험 제안</dt>
          <dd>
            <span v-if="list(t.experiment.datasets).length">데이터셋 {{ list(t.experiment.datasets).join(', ') }}</span>
            <span v-if="list(t.experiment.baselines).length">비교 대상 {{ list(t.experiment.baselines).join(', ') }}</span>
            <span v-if="list(t.experiment.metrics).length">지표 {{ list(t.experiment.metrics).join(', ') }}</span>
          </dd>
        </div>
        <div v-if="list(t.based_on).length">
          <dt>근거가 된 한계</dt>
          <dd class="chips"><CiteChip v-for="label in list(t.based_on)" :key="label" :label="label" @cite="$emit('cite', $event)" /></dd>
        </div>
        <div v-if="list(t.similar_papers).length" class="similar">
          <dt>라이브러리 안의 유사 연구</dt>
          <dd>
            <RouterLink v-for="p in list(t.similar_papers)" :key="p.paper_id" :to="{ name: 'paper', params: { id: p.paper_id } }">{{ p.title }}</RouterLink>
            이미 비슷한 연구가 있어요. 차별점을 확인하세요.
          </dd>
        </div>
      </dl>
    </li>
  </ul>
</template>

<style scoped>
.cards {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
  gap: 12px;
}

.card {
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-m);
  background: var(--c-paper);
  display: grid;
  gap: 8px;
  align-content: start;
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: var(--fs-xs);
}

.persp {
  background: var(--c-accent-2-wash);
  color: var(--c-ink);
}

.ai {
  background: var(--c-accent-wash);
  color: var(--c-accent-ink);
}

h3 {
  font-size: var(--fs-md);
  line-height: 1.4;
  overflow-wrap: anywhere;
}

dl {
  margin: 0;
  display: grid;
  gap: 8px;
  font-size: var(--fs-sm);
}

dt {
  color: var(--c-ink-muted);
  font-size: var(--fs-xs);
}

dd {
  margin: 0;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

dd span + span::before {
  content: ' · ';
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.similar dd a {
  display: block;
}
</style>
