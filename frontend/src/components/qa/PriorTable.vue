<script setup>
import { EMPTY_CELL, PRIOR_COLUMNS } from '@/lib/modes'
import CiteChip from './CiteChip.vue'

// 선행연구 정리표: 논문마다 한 행. 칸의 근거 라벨은 알약으로 보여 주고 누르면 근거 목록이 그 줄을 강조한다.
// 값이 없으면 지어내지 않고 '논문에 명시되지 않음'을 회색으로 보인다. 좁은 화면에서는 논문별 카드로 바뀐다.
defineProps({ rows: { type: Array, required: true } })
defineEmits(['cite'])

const textOf = (row, key) => String(row[key] ?? '').replace(/\s+/g, ' ').trim()
</script>

<template>
  <div class="scroll" tabindex="0" role="region" aria-label="선행연구 정리표">
    <table class="prior">
      <thead>
        <tr>
          <th scope="col">논문</th>
          <th v-for="[key, name] in PRIOR_COLUMNS" :key="key" scope="col">{{ name }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.paper_id">
          <th scope="row" class="title">{{ row.title }}</th>
          <td v-for="[key, name] in PRIOR_COLUMNS" :key="key" :data-label="name">
            <template v-if="textOf(row, key)">
              {{ textOf(row, key) }}
              <CiteChip v-if="row.labels?.[key]" :label="row.labels[key]" @cite="$emit('cite', $event)" />
            </template>
            <span v-else class="empty">{{ EMPTY_CELL }}</span>
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

.prior {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}

.prior th,
.prior td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--c-rule);
  text-align: left;
  vertical-align: top;
  line-height: 1.55;
}

.prior thead th {
  background: var(--c-surface);
  white-space: nowrap;
}

.prior tbody tr:last-child > * {
  border-bottom: 0;
}

.title {
  min-width: 150px;
  font-weight: 600;
}

.empty {
  color: var(--c-ink-muted);
}

@media (max-width: 640px) {
  .scroll {
    overflow: visible;
    border: 0;
  }

  .prior,
  .prior tbody,
  .prior tr,
  .prior th,
  .prior td {
    display: block;
    min-width: 0;
  }

  .prior thead {
    display: none;
  }

  .prior tr {
    margin-bottom: 12px;
    border: 1px solid var(--c-rule);
    border-radius: var(--radius-m);
    overflow: hidden;
  }

  .prior td::before {
    content: attr(data-label);
    display: block;
    color: var(--c-ink-muted);
    font-size: var(--fs-xs);
  }
}
</style>
