<script setup>
import { nextTick, ref, useId, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { safeUrl, toneOfLabel } from '@/lib/format'
import Icon from '@/components/common/Icon.vue'

// 답변 아래 회청색 근거 상자. 본문의 출처 알약을 누르면 같은 색 줄로 옮겨 가 강조한다.
const props = defineProps({
  items: { type: Array, default: () => [] }, // source_details: { label, paper_id, title, page, url, snippet }
  fallback: { type: Array, default: () => [] }, // sources: "논문명 p.N" 문자열(상세가 없을 때만)
  active: { type: Object, default: null }, // { label, n } 본문에서 누른 근거
})

const uid = useId()
const current = ref(null)

watch(
  () => props.active,
  async (a) => {
    if (!a) return
    current.value = a.label
    await nextTick()
    const el = document.getElementById(`${uid}-${a.label}`)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el?.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' })
    el?.focus({ preventScroll: true })
  },
)
</script>

<template>
  <section class="callout info" :aria-labelledby="`${uid}-title`">
    <Icon name="forward" />
    <div>
      <h3 :id="`${uid}-title`" class="section-label">근거 {{ items.length || fallback.length }}건</h3>
      <ol v-if="items.length" class="list">
        <li v-for="s in items" :id="`${uid}-${s.label}`" :key="s.label" tabindex="-1" :class="{ on: current === s.label }">
          <span class="ref" :data-tone="toneOfLabel(s.label)">{{ s.label }}</span>
          <div class="body">
            <p class="where">
              <RouterLink v-if="s.paper_id" :to="{ name: 'paper', params: { id: s.paper_id }, query: s.page ? { page: s.page } : {} }">{{ s.title }}</RouterLink>
              <a v-else-if="safeUrl(s.url)" :href="safeUrl(s.url)" target="_blank" rel="noopener noreferrer">{{ s.title }}</a>
              <span v-else>{{ s.title }}</span>
              <span v-if="s.page" class="page tabular">{{ s.page }}쪽</span>
            </p>
            <p v-if="s.snippet" class="quote">{{ s.snippet }}</p>
          </div>
        </li>
      </ol>
      <ul v-else class="plain">
        <li v-for="s in fallback" :key="s">{{ s }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.list {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 2px;
}

li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  padding: 8px;
  margin: 0 -8px;
  border-radius: var(--radius-m);
  transition: background-color 0.4s ease;
}

li:focus {
  outline: none;
}

/* 본문 출처를 누르면 그 줄을 피그마 선택 상자처럼 파란 테두리와 모서리 손잡이로 표시 */
li {
  position: relative;
}

li.on {
  background: var(--c-glass-strong);
  box-shadow: inset 0 0 0 1.5px var(--c-accent-2);
  border-radius: 2px;
}

li.on::before,
li.on::after {
  content: "";
  position: absolute;
  width: 7px;
  height: 7px;
  border: 1.5px solid var(--c-accent-2);
  background: var(--c-paper);
}

li.on::before {
  top: -3px;
  left: -3px;
}

li.on::after {
  right: -3px;
  bottom: -3px;
}

.ref {
  align-self: start;
}

.where {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 10px;
}

.where a,
.where span:first-child {
  color: var(--c-ink);
  font-weight: 600;
  text-decoration: none;
}

.where a:hover {
  text-decoration: underline;
}

.page {
  color: var(--c-ink-muted);
  font-size: var(--fs-xs);
}

.quote {
  margin-top: 3px;
  color: var(--c-ink-muted);
  line-height: 1.55;
}

.plain {
  margin: 8px 0 0;
  padding-left: 1.2em;
}
</style>
