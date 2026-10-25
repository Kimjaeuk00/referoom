<script setup>
import { formatDelta, verdictOf } from '@/lib/modes'
import CiteChip from './CiteChip.vue'

// 원고 주장별 대조표. 판정은 색만으로 구분하지 않도록 아이콘·글자·색을 함께 쓴다.
// 서버가 만든 문자열은 모두 텍스트 보간으로만 그린다.
defineProps({ claims: { type: Array, required: true } })
defineEmits(['cite', 'collect'])

const empty = '—'
</script>

<template>
  <div class="scroll" tabindex="0" role="region" aria-label="원고 대조표">
    <table class="verify">
      <thead>
        <tr>
          <th scope="col">원고 문장</th>
          <th scope="col">원고 값</th>
          <th scope="col">논문 값</th>
          <th scope="col">조건</th>
          <th scope="col">판정</th>
          <th scope="col">출처</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(c, i) in claims" :key="i">
          <th scope="row" class="sentence">{{ c.sentence }}</th>
          <td data-label="원고 값">{{ c.claimed_value ?? empty }}<span v-if="c.metric" class="sub">{{ c.metric }}</span></td>
          <td data-label="논문 값">
            <template v-if="c.verdict === 'own_result'">{{ formatDelta(c.delta) || empty }}</template>
            <template v-else>{{ c.found_value ?? empty }}</template>
          </td>
          <td data-label="조건">{{ c.condition ?? c.dataset ?? empty }}</td>
          <td data-label="판정">
            <span class="verdict" :data-tone="verdictOf(c.verdict).tone" :title="verdictOf(c.verdict).desc">
              <span aria-hidden="true">{{ verdictOf(c.verdict).icon }}</span> {{ verdictOf(c.verdict).label }}
            </span>
            <button v-if="c.verdict === 'not_found'" type="button" class="btn collect" @click="$emit('collect', c)">선행연구로 수집하기</button>
          </td>
          <td data-label="출처" class="cites">
            <CiteChip v-for="label in c.labels ?? []" :key="label" :label="label" @cite="$emit('cite', $event)" />
            <span v-if="!(c.labels ?? []).length" class="sub">{{ empty }}</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.scroll {
  overflow-x: auto;
  border: 1px solid var(--c-rule);
  border-radius: var(--radius-m);
}

.verify {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}

.verify th,
.verify td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--c-rule);
  text-align: left;
  vertical-align: top;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.verify thead th {
  background: var(--c-surface);
  white-space: nowrap;
}

.verify tbody tr:last-child > * {
  border-bottom: 0;
}

.sentence {
  min-width: 180px;
  font-weight: 600;
}

.sub {
  display: block;
  color: var(--c-ink-muted);
  font-size: var(--fs-xs);
}

.cites {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.verdict {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border: 1px solid currentColor;
  border-radius: 999px;
  font-weight: 600;
  white-space: nowrap;
}

.verdict[data-tone='good'] { color: var(--c-ok); }
.verdict[data-tone='bad'] { color: var(--c-danger); }
.verdict[data-tone='warn'] { color: var(--c-review); }
.verdict[data-tone='muted'] { color: var(--c-ink-muted); }
.verdict[data-tone='info'] { color: var(--c-accent-2); }

.collect {
  display: block;
  margin-top: 6px;
}

@media (max-width: 640px) {
  .scroll {
    overflow: visible;
    border: 0;
  }

  .verify,
  .verify tbody,
  .verify tr,
  .verify th,
  .verify td {
    display: block;
    min-width: 0;
  }

  .verify thead {
    display: none;
  }

  .verify tr {
    margin-bottom: 12px;
    border: 1px solid var(--c-rule);
    border-radius: var(--radius-m);
    overflow: hidden;
  }

  .verify td::before {
    content: attr(data-label);
    display: block;
    color: var(--c-ink-muted);
    font-size: var(--fs-xs);
  }
}
</style>
