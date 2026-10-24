<script setup>
import { authorsShort, formatDate, PAPER_STATUS, SOURCE_TYPE, toneOfTag } from '@/lib/format'
import Icon from '@/components/common/Icon.vue'

// GET /papers의 items: { id, title, authors, year, source_type, tags, status, chunk_count, url, created_at } (+ error_msg, added_by)
defineProps({
  items: { type: Array, required: true },
  canDelete: { type: Function, required: true },
})
defineEmits(['open', 'delete'])
</script>

<template>
  <table class="papers data-table">
    <thead>
      <tr>
        <th scope="col">논문</th>
        <th scope="col">출처</th>
        <th scope="col">태그</th>
        <th scope="col">상태</th>
        <th scope="col" class="num">청크</th>
        <th scope="col">등록일</th>
        <th scope="col"><span class="visually-hidden">작업</span></th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="p in items" :key="p.id" @click="$emit('open', p)">
        <td class="title-cell">
          <div class="title-wrap">
            <button type="button" class="title" @click.stop="$emit('open', p)">{{ p.title }}</button>
            <span class="hint">{{ [authorsShort(p.authors), p.year].filter(Boolean).join(', ') }}</span>
          </div>
        </td>
        <td data-label="출처">{{ SOURCE_TYPE[p.source_type] ?? p.source_type }}</td>
        <td data-label="태그">
          <span v-for="t in p.tags" :key="t" class="tag" :class="toneOfTag(t)">{{ t }}</span>
        </td>
        <td data-label="상태">
          <span class="status" :class="p.status">{{ PAPER_STATUS[p.status] ?? p.status }}</span>
          <span v-if="p.status === 'failed' && p.error_msg" class="reason">{{ p.error_msg }}</span>
        </td>
        <td data-label="청크" class="num tabular">{{ p.chunk_count ?? '–' }}</td>
        <td data-label="등록일" class="tabular">{{ formatDate(p.created_at) }}</td>
        <td class="actions">
          <button
            v-if="canDelete(p)"
            type="button"
            class="del"
            :aria-label="`'${p.title}' 삭제`"
            title="삭제"
            @click.stop="$emit('delete', p)"
          >
            <Icon name="trash" :size="18" />
          </button>
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.papers td {
  white-space: nowrap;
}

.papers .title-cell,
.papers td[data-label="태그"] {
  white-space: normal;
}

tbody tr {
  cursor: pointer;
}

tbody tr:hover {
  background: var(--c-surface);
}

.title-cell {
  min-width: 260px;
}

.title-wrap {
  display: grid;
  gap: 2px;
}

.title {
  padding: 0;
  border: 0;
  background: none;
  font-weight: 500;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
}

.title:hover {
  color: var(--c-accent);
  text-decoration: underline;
}

.reason {
  display: block;
  margin-top: 2px;
  color: var(--c-danger);
  font-size: var(--fs-xs);
}

.actions {
  width: 1%;
  text-align: right;
  vertical-align: middle;
}

/* 휴지통 아이콘: 평소엔 옅게, 줄에 마우스를 올리거나 키보드로 고르면 또렷하게, 누를 자리에선 빨강 */
.del {
  width: 32px;
  height: 32px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--c-ink-muted);
  opacity: 0.35;
  cursor: pointer;
  transition: opacity 0.15s ease, background-color 0.15s ease, color 0.15s ease;
}

tbody tr:hover .del,
.del:focus-visible {
  opacity: 1;
}

.del:hover {
  background: var(--c-danger-wash);
  color: var(--c-danger);
}

/* 마우스가 없는 화면(터치)에서는 늘 보이게 */
@media (hover: none) {
  .del {
    opacity: 1;
  }
}

/* 좁은 화면에서는 표를 논문별 블록으로 바꾼다 */
@media (max-width: 720px) {
  thead {
    display: none;
  }

  table,
  tbody,
  tr,
  td {
    display: block;
  }

  tr {
    padding: 12px;
    border-bottom: 1px solid var(--c-rule);
  }

  tbody tr:last-child {
    border-bottom: 0;
  }

  .papers td {
    padding: 2px 0;
    border: 0;
  }

  td[data-label] {
    display: flex;
    gap: 8px;
  }

  td[data-label]::before {
    content: attr(data-label);
    flex: 0 0 52px;
    color: var(--c-ink-muted);
    font-size: var(--fs-xs);
  }

  .title-cell {
    min-width: 0;
    padding-bottom: 6px;
  }

  .papers .num {
    text-align: left;
  }

  /* 카드 모양에서는 휴지통을 오른쪽 위 모서리에 */
  tr {
    position: relative;
  }

  .papers .actions {
    position: absolute;
    top: 8px;
    right: 6px;
    width: auto;
    padding: 0;
  }

  .papers .title-cell {
    padding-right: 36px;
  }
}
</style>
