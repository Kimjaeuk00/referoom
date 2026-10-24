<script setup>
import { computed, ref } from 'vue'
import { authorsShort, toneOfTag } from '@/lib/format'
import Icon from '@/components/common/Icon.vue'

// 질문하기 왼쪽 패널: 색인된 논문 목록에서 질문 범위를 고른다.
// 아무것도 고르지 않으면 팀 전체, 고르면 scope { type: 'paper', ids }로 보낸다(DEV_04 2.1).
const props = defineProps({
  papers: { type: Array, default: () => [] },
  modelValue: { type: Array, default: () => [] }, // 고른 논문 id
})
const emit = defineEmits(['update:modelValue'])

const q = ref('')
// 제목·저자·태그로 찾는다. 태그 이름을 치고 "모두 선택"하면 태그 범위와 같은 효과다.
const visible = computed(() => {
  const term = q.value.trim().toLowerCase()
  if (!term) return props.papers
  return props.papers.filter((p) => [p.title, p.authors, ...(p.tags ?? [])].some((v) => String(v ?? '').toLowerCase().includes(term)))
})

const picked = computed(() => new Set(props.modelValue))
const pickedVisible = computed(() => visible.value.filter((p) => picked.value.has(p.id)).length)
const allVisible = computed(() => visible.value.length > 0 && pickedVisible.value === visible.value.length)

function toggle(id) {
  const next = new Set(picked.value)
  next.has(id) ? next.delete(id) : next.add(id)
  emit('update:modelValue', [...next])
}

function toggleAll() {
  const next = new Set(picked.value)
  for (const p of visible.value) allVisible.value ? next.delete(p.id) : next.add(p.id)
  emit('update:modelValue', [...next])
}
</script>

<template>
  <section class="picker" aria-labelledby="picker-title">
    <h2 id="picker-title" class="visually-hidden">질문할 논문 고르기</h2>
    <div class="search">
      <Icon name="search" :size="18" />
      <label class="visually-hidden" for="picker-q">논문 찾기</label>
      <input id="picker-q" v-model="q" type="search" placeholder="제목, 저자, 태그" />
    </div>

    <label class="all">
      <input
        type="checkbox"
        :checked="allVisible"
        :indeterminate="pickedVisible > 0 && !allVisible"
        :disabled="!visible.length"
        @change="toggleAll"
      />
      <span>{{ q ? `찾은 ${visible.length}편 모두` : `${visible.length}편 모두` }}</span>
    </label>
    <p class="scope-note">
      {{ modelValue.length ? `고른 ${modelValue.length}편에서만 근거를 찾아요.` : '고르지 않으면 팀 전체에서 찾아요.' }}
    </p>

    <ul v-if="visible.length" class="list">
      <li v-for="p in visible" :key="p.id" :class="{ on: picked.has(p.id) }">
        <label class="item">
          <input type="checkbox" :checked="picked.has(p.id)" @change="toggle(p.id)" />
          <Icon name="doc" :size="18" class="doc" />
          <span class="body">
            <span class="title">{{ p.title }}</span>
            <span class="meta">{{ [authorsShort(p.authors), p.year].filter(Boolean).join(', ') }}</span>
            <span v-if="p.tags?.length" class="tags">
              <span v-for="t in p.tags" :key="t" class="pill" :class="toneOfTag(t)">{{ t }}</span>
            </span>
          </span>
        </label>
      </li>
    </ul>
    <p v-else class="empty">{{ q ? `'${q}'에 맞는 논문이 없어요.` : '색인된 논문이 아직 없어요.' }}</p>

    <slot />
  </section>
</template>

<style scoped>
.picker {
  display: grid;
  grid-template-columns: minmax(0, 1fr); /* 패널이 좁아져도 안쪽이 따라 줄게 */
  gap: 10px;
  align-content: start;
}

.search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--c-rule-strong);
  border-radius: 999px;
  background: var(--c-paper);
  color: var(--c-ink-muted);
}

.search:focus-within {
  border-color: var(--c-accent-2);
  box-shadow: 0 0 0 1px var(--c-accent-2);
}

.search input {
  flex: 1;
  width: 0; /* 입력칸 기본 너비(약 20글자)가 패널을 밀어 넓히지 않게 */
  min-width: 0;
  border: 0;
  background: none;
  font-size: var(--fs-sm);
  color: var(--c-ink);
}

.search input:focus-visible {
  outline: none;
}

input[type="checkbox"] {
  width: 16px;
  height: 16px;
  margin: 0;
  accent-color: var(--c-accent);
  flex: none;
}

.all {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 2px 0;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.scope-note {
  padding: 0 2px 8px;
  border-bottom: 1px solid var(--c-rule);
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.list li + li {
  border-top: 1px solid var(--c-rule);
}

.item {
  display: grid;
  grid-template-columns: 16px 18px 1fr;
  gap: 10px;
  padding: 12px 2px;
  cursor: pointer;
}

.item input,
.doc {
  margin-top: 2px;
}

.doc {
  color: var(--c-ink-muted);
}

.on .doc {
  color: var(--c-accent);
}

.body {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.title {
  font-size: var(--fs-sm);
  font-weight: 600;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.tags {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.empty {
  padding: 12px 2px;
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}
</style>
