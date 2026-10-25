<script setup>
import { computed, ref } from 'vue'
import { renderMarkdown } from '@/lib/markdown'
import { toast } from '@/composables/useToast'
import Icon from '@/components/common/Icon.vue'
import ReviewBadge from './ReviewBadge.vue'
import SourceList from './SourceList.vue'
import VerifyTable from './VerifyTable.vue'

// 검증 결과: 경고 → 대조표 → 비교 문장 초안 → 검토 안내 → 근거 목록. 수치를 다루므로 검토 안내는 항상 보인다.
const props = defineProps({
  result: { type: Object, required: true }, // { claims, draft, warnings, sources, source_details, needs_review, handoff }
  params: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
  active: { type: Object, default: null },
})
const emit = defineEmits(['cite', 'collect', 'reask', 'add-paper', 'ask-team', 'research', 'pick-papers'])

const details = computed(() => props.result.source_details ?? [])
const claims = computed(() => props.result.claims ?? [])
const warnings = computed(() => props.result.warnings ?? [])
const allNotFound = computed(() => props.result.handoff || (claims.value.length > 0 && claims.value.every((c) => c.verdict === 'not_found')))
const scopeNote = computed(() => (props.params.paperIds?.length ? `선택한 논문 ${props.params.paperIds.length}편과 비교했어요.` : '전체 라이브러리에서 찾았어요.'))

const draftHtml = computed(() => (props.result.draft ? renderMarkdown(props.result.draft, new Set(details.value.map((d) => d.label))) : ''))
const draftBox = ref(null)

function onDraftClick(event) {
  const chip = event.target.closest('button.cite')
  if (chip) emit('cite', chip.dataset.label)
}

async function copyDraft() {
  try {
    await navigator.clipboard.writeText(draftBox.value?.innerText ?? props.result.draft)
    toast('비교 문장 초안을 복사했어요.')
  } catch {
    toast('복사하지 못했어요. 글을 직접 선택해 복사하세요.', { tone: 'error' })
  }
}
</script>

<template>
  <div class="verify-result">
    <p class="hint">{{ scopeNote }}</p>

    <div v-if="allNotFound" class="callout info" role="status">
      <Icon name="forward" />
      <div>
        <p class="callout-title">라이브러리에서 비교할 값을 찾지 못했어요</p>
        <p class="text">원고의 주장과 맞는 선행연구가 아직 없어요. 아래에서 선행연구로 논문을 먼저 모아 보세요.</p>
      </div>
    </div>

    <ul v-if="warnings.length" class="warnings">
      <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
    </ul>

    <VerifyTable v-if="claims.length" :claims="claims" @cite="emit('cite', $event)" @collect="emit('collect', $event)" />

    <section v-if="draftHtml" class="draft" aria-label="비교 문장 초안">
      <div class="draft-head">
        <h3>비교 문장 초안</h3>
        <button type="button" class="icon-btn" title="초안 복사" aria-label="초안 복사" @click="copyDraft"><Icon name="copy" :size="18" /></button>
      </div>
      <div ref="draftBox" class="prose" @click="onDraftClick" v-html="draftHtml" />
      <p class="hint">AI가 쓴 초안이에요. 논문에 넣기 전에 원문과 대조하세요.</p>
    </section>

    <ReviewBadge text="" :sources="details" />
    <SourceList v-if="details.length" :items="details" :fallback="result.sources ?? []" :active="active" />
  </div>
</template>

<style scoped>
.verify-result {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.warnings {
  margin: 0;
  padding-left: 1.2em;
  font-size: var(--fs-sm);
  color: var(--c-review);
}

.draft {
  display: grid;
  gap: 8px;
  padding: 12px 16px;
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-m);
  background: var(--c-paper);
}

.draft-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.draft-head h3 {
  font-size: var(--fs-md);
}

.prose {
  max-width: 68ch;
  line-height: 1.75;
}
</style>
