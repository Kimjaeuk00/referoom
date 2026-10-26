<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  scope: { type: Object, required: true }, // { type: 'all' } | { type: 'paper', ids }
  papers: { type: Array, default: () => [] },
  pickedTitle: { type: String, default: '' }, // 목록을 아직 못 받았을 때 보여줄 논문 제목
})
const emit = defineEmits(['update:scope'])

const MODES = [
  ['all', '팀 전체'],
  ['paper', '논문 한 편'],
]

const mode = computed(() => props.scope?.type ?? 'all')
const search = ref('')

function setMode(type) {
  if (type === mode.value) return
  emit('update:scope', type === 'paper' ? { type, ids: [] } : { type: 'all' })
}

const picked = computed(() => {
  const id = props.scope.type === 'paper' ? props.scope.ids?.[0] : null
  if (!id) return null
  return props.papers.find((p) => p.id === id) ?? { id, title: props.pickedTitle || '선택한 논문' }
})

const matches = computed(() => {
  const q = search.value.trim().toLowerCase()
  return props.papers.filter((p) => !q || p.title.toLowerCase().includes(q)).slice(0, 8)
})

function pick(paper) {
  emit('update:scope', { type: 'paper', ids: [paper.id] })
  search.value = ''
}
</script>

<template>
  <div class="scope">
    <fieldset>
      <legend class="label">범위</legend>
      <div class="modes">
        <label v-for="[key, name] in MODES" :key="key" class="mode">
          <input type="radio" name="scope-mode" :value="key" :checked="mode === key" @change="setMode(key)" />
          {{ name }}
        </label>
      </div>

      <div v-if="mode === 'paper'" class="sub">
        <div v-if="picked" class="picked">
          <span class="picked-title">{{ picked.title }}</span>
          <button type="button" class="btn-quiet change" @click="emit('update:scope', { type: 'paper', ids: [] })">바꾸기</button>
        </div>
        <template v-else>
          <input v-model="search" class="input" type="search" placeholder="논문 제목으로 찾기" aria-label="논문 제목으로 찾기" />
          <ul class="matches">
            <li v-for="p in matches" :key="p.id">
              <button type="button" @click="pick(p)">
                <span>{{ p.title }}</span>
                <span class="hint">{{ p.year }}</span>
              </button>
            </li>
            <li v-if="!matches.length" class="hint none">맞는 논문이 없어요.</li>
          </ul>
        </template>
      </div>
    </fieldset>
  </div>
</template>

<style scoped>
.scope {
  display: grid;
  gap: 20px;
}

fieldset {
  display: grid;
  gap: 8px;
}

.modes {
  display: grid;
  gap: 4px;
}

.mode {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-sm);
  cursor: pointer;
}

.mode input {
  accent-color: var(--c-accent);
}

.sub {
  margin-top: 4px;
}

.picked {
  display: grid;
  gap: 2px;
  padding: 8px 10px;
  border: 1px solid var(--c-accent);
  border-radius: var(--radius-m);
  background: var(--c-surface);
  font-size: var(--fs-sm);
}

.picked-title {
  font-weight: 500;
  line-height: 1.4;
}

.change {
  justify-self: start;
  padding: 0;
  min-height: 0;
  font-size: var(--fs-xs);
}

.matches {
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--c-rule);
  border-radius: var(--radius-m);
  background: var(--c-surface);
}

.matches button {
  width: 100%;
  display: grid;
  gap: 0;
  padding: 8px 10px;
  border: 0;
  border-bottom: 1px solid var(--c-rule);
  background: none;
  text-align: left;
  font-size: var(--fs-sm);
  line-height: 1.4;
  cursor: pointer;
}

.matches li:last-child button {
  border-bottom: 0;
}

.matches button:hover {
  background: var(--c-accent-wash);
}

.none {
  padding: 8px 10px;
}
</style>
