<script setup>
import { CHIP_MODES, MODES } from '@/lib/modes'

// 연구 모드를 켰을 때 선행연구·주제·검증 중 하나를 고른다. 끄는 것은 ResearchToggle이 맡는다(켠 칩을 다시 눌러도 그대로다).
defineProps({
  modelValue: { type: String, default: 'prior' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <div class="segmented" role="group" aria-label="연구 모드 종류">
    <button v-for="mode in CHIP_MODES" :key="mode" type="button" :aria-pressed="modelValue === mode" :title="MODES[mode].hint" :disabled="disabled" @click="emit('update:modelValue', mode)">
      {{ MODES[mode].label }}
    </button>
  </div>
</template>
