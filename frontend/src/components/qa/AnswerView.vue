<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/lib/markdown'
import { canReask, reaskLevel } from '@/lib/levels'
import SourceList from './SourceList.vue'
import HandoffNotice from './HandoffNotice.vue'
import Icon from '@/components/common/Icon.vue'
import { toast } from '@/composables/useToast'

const props = defineProps({
  result: { type: Object, required: true }, // { answer, sources, source_details, needs_review, handoff, level, latency_ms }
  params: { type: Object, required: true }, // 이 답을 받을 때 보낸 값. 더 쉽게/더 깊게일 때만 level이 있다
  busy: { type: Boolean, default: false },
  active: { type: Object, default: null }, // { label, n } 눌린 근거. TurnResult가 갖고 있다가 근거 목록에 넘긴다
  reaskable: { type: Boolean, default: true }, // 음성 튜터에서는 다시 묻기 대신 다시 말한다
})
const emit = defineEmits(['reask', 'add-paper', 'ask-team', 'cite'])

const details = computed(() => props.result.source_details ?? [])
const hasSources = computed(() => details.value.length > 0 || (props.result.sources?.length ?? 0) > 0)
// 출처가 없는 답은 "출처 없음"으로 보여주지 않고 handoff로 처리한다(DEV_02 4.6)
const isHandoff = computed(() => props.result.handoff || !hasSources.value)

// Vorb처럼 답 아래 복사 아이콘. 근거 라벨([S1] 등)은 빼고 답변 원문만 복사한다.
async function copyAnswer() {
  try {
    const text = props.result.answer.replace(/[ \t]*\[S\d{1,3}\]/g, '')
    await navigator.clipboard.writeText(text)
    toast('답변을 복사했어요.')
  } catch {
    toast('복사하지 못했어요. 글을 직접 선택해 복사하세요.', { tone: 'error' })
  }
}

const html = computed(() => renderMarkdown(props.result.answer, new Set(details.value.map((d) => d.label))))

// 본문의 알약(v-html 안의 button.cite)은 이벤트 위임으로 받아 라벨만 알린다
function onBodyClick(event) {
  const chip = event.target.closest('button.cite')
  if (chip) emit('cite', chip.dataset.label)
}

const depth = computed(() => props.params.level ?? null) // 지금 답변의 깊이: L1(쉬움) | null(기본) | L3(깊음)
</script>

<template>
  <HandoffNotice v-if="isHandoff" @add-paper="emit('add-paper')" @ask-team="emit('ask-team')" />
  <div v-else class="answer">
    <div class="prose" @click="onBodyClick" v-html="html" />
    <slot name="after-body" />
    <SourceList :items="details" :fallback="result.sources ?? []" :active="active" :needs-review="!!result.needs_review" />
    <div class="reask" role="group" aria-label="이 답변으로 할 수 있는 일">
      <template v-if="reaskable">
        <button type="button" class="btn" :disabled="busy || !canReask(depth, 'easier')" @click="emit('reask', { level: reaskLevel(depth, 'easier') })">더 쉽게</button>
        <button type="button" class="btn" :disabled="busy || !canReask(depth, 'deeper')" @click="emit('reask', { level: reaskLevel(depth, 'deeper') })">더 깊게</button>
      </template>
      <slot />
      <button type="button" class="icon-btn copy" title="답변 복사" aria-label="답변 복사" @click="copyAnswer"><Icon name="copy" :size="18" /></button>
    </div>
  </div>
</template>

<style scoped>
/* 시안 순서: 답변 본문 → 원문 확인 권장 → 근거 상자 → 다시 묻기 */
.answer {
  display: grid;
  grid-template-columns: minmax(0, 1fr); /* 긴 수식은 가로 스크롤, 열은 넓히지 않는다 */
  gap: 16px;
}

/* 답변 본문: alphaXiv 본문과 같은 16px / 28px */
.prose {
  max-width: 68ch;
  font-size: var(--fs-md);
  line-height: 1.75;
}

.prose :deep(p + p),
.prose :deep(p + ul),
.prose :deep(ul + p),
.prose :deep(p + ol) {
  margin-top: 0.9em;
}

.prose :deep(ul),
.prose :deep(ol) {
  margin: 0;
  padding-left: 1.3em;
}

.prose :deep(li + li) {
  margin-top: 0.3em;
}

.prose :deep(code) {
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--c-accent-wash);
  font-size: 0.9em;
}

.prose :deep(pre) {
  overflow-x: auto;
  padding: 12px;
  background: var(--c-surface);
  border: 1px solid var(--c-rule);
  border-radius: var(--radius-m);
}

.prose :deep(.katex-display) {
  margin: 1em 0;
  overflow-x: auto;
  overflow-y: hidden;
}

.reask {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.copy {
  margin-left: auto;
  color: var(--c-ink-muted);
}
</style>
