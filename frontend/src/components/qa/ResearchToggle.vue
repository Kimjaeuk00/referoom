<script setup>
// 연구 모드 스위치. 꺼져 있으면 튜터(근거 기반 Q&A)이고, 켜면 선행연구·주제·검증 중 하나를 고를 수 있다(ModeChips).
defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
</script>

<template>
  <button
    type="button"
    class="research-toggle"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    title="켜면 선행연구·주제·검증 모드를 쓸 수 있어요. 끄면 논문 내용을 묻는 튜터로 돌아와요."
    @click="emit('update:modelValue', !modelValue)"
  >
    <span class="track" aria-hidden="true"><span class="thumb" /></span>
    <span class="label">연구 모드</span>
  </button>
</template>

<style scoped>
.research-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 0 12px 0 8px;
  border: 0;
  border-radius: 999px;
  background: none;
  color: var(--c-ink);
  font-size: var(--fs-md);
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.research-toggle:hover:not(:disabled) {
  background: var(--c-surface);
}

.research-toggle:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.track {
  position: relative;
  width: 34px;
  height: 20px;
  border-radius: 999px;
  background: var(--c-rule-strong);
  transition: background 0.15s ease;
}

.thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--c-paper);
  transition: transform 0.15s ease;
}

.research-toggle[aria-checked="true"] .track {
  background: var(--c-black);
}

.research-toggle[aria-checked="true"] .thumb {
  transform: translateX(14px);
}

@media (prefers-reduced-motion: reduce) {
  .track,
  .thumb {
    transition: none;
  }
}
</style>
