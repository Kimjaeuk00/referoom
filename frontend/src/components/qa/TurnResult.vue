<script setup>
import { computed, ref } from 'vue'
import StatusBanner from '@/components/common/StatusBanner.vue'
import SpeakButton from '@/components/voice/SpeakButton.vue'
import { voiceAvailable } from '@/lib/voice'
import AnswerView from './AnswerView.vue'

// 질문 한 건의 결과(로딩·오류·답변)를 모드에 맞는 화면으로 그린다.
// 눌린 인용(근거) 상태는 여기서 한 곳이 갖고, 결과 화면과 근거 목록(SourceList)이 함께 쓴다.
const props = defineProps({
  turn: { type: Object, required: true }, // stores/qa.js의 turn: { status, slow, result, error, params }
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['retry', 'reask', 'add-paper', 'ask-team'])

// 모드별 결과 화면. 선행연구·주제·검증 화면은 만들어지는 대로 여기에 등록한다.
const RESULT_VIEWS = { tutor: AnswerView }
const resultView = computed(() => RESULT_VIEWS[props.turn.params.mode ?? 'tutor'])

const active = ref(null) // { label, n }: 누른 근거. n이 바뀔 때마다 근거 목록이 그 줄로 옮겨 가 강조한다
let clicks = 0
const onCite = (label) => (active.value = { label, n: ++clicks })
</script>

<template>
  <div v-if="turn.status === 'loading'" class="pending">
    <div class="skeleton" aria-hidden="true"><span></span><span></span><span></span></div>
    <p class="hint">{{ turn.slow ? '조금 더 걸리고 있어요.' : '근거를 찾고 답변을 쓰는 중이에요.' }}</p>
  </div>
  <StatusBanner v-else-if="turn.status === 'error'" :message="turn.error.message" :retry="turn.error.retryable" @retry="emit('retry')" />
  <component
    :is="resultView"
    v-else
    :result="turn.result"
    :params="turn.params"
    :busy="busy"
    :active="active"
    @reask="emit('reask', $event)"
    @add-paper="emit('add-paper')"
    @ask-team="emit('ask-team')"
    @cite="onCite"
  >
    <SpeakButton v-if="voiceAvailable" :text="turn.result.answer" />
  </component>
</template>

<style scoped>
.pending {
  max-width: 62ch;
  display: grid;
  gap: 12px;
}
</style>
