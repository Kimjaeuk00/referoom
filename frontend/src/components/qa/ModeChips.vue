<script setup>
import { CHIP_MODES, MODES } from '@/lib/modes'

// 선행연구·주제·검증 중 하나를 켜는 칩. 켠 칩을 다시 누르면 꺼지고 튜터가 된다. 어느 것도 켜지 않은 상태가 튜터다.
const props = defineProps({
  modelValue: { type: String, default: 'tutor' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const toggle = (mode) => emit('update:modelValue', props.modelValue === mode ? 'tutor' : mode)
</script>

<template>
  <div class="segmented" role="group" aria-label="질문 모드">
    <button v-for="mode in CHIP_MODES" :key="mode" type="button" :aria-pressed="modelValue === mode" :title="MODES[mode].hint" :disabled="disabled" @click="toggle(mode)">
      {{ MODES[mode].label }}
    </button>
  </div>
</template>
