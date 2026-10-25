<script setup>
import { toneOfLabel } from '@/lib/format'

// 표·카드 칸 안의 [S#] 근거 알약. 답변 본문의 알약(lib/markdown.js가 만드는 button.cite)과 같은 .cite 스타일(styles/base.css)을 쓴다.
// 누르면 cite 이벤트로 라벨을 알리고, 근거 목록(SourceList)이 그 줄을 강조하는 일은 TurnResult가 이어 준다.
defineProps({ label: { type: String, required: true } })
defineEmits(['cite'])
</script>

<template>
  <button type="button" class="cite" :data-label="label" :data-tone="toneOfLabel(label)" :aria-label="`근거 ${label} 보기`" @click="$emit('cite', label)">{{ label }}</button>
</template>
