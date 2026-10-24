<script setup>
import { dismissToast, useToasts } from '@/composables/useToast'

const toasts = useToasts()
</script>

<template>
  <div class="toasts" role="status" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.tone">
      <span>{{ t.message }}</span>
      <button type="button" class="close" aria-label="알림 닫기" @click="dismissToast(t.id)">닫기</button>
    </div>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 50;
  display: grid;
  gap: 8px;
  max-width: min(420px, calc(100vw - 32px));
}

.toast {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 14px;
  border-radius: var(--radius-m);
  background: var(--c-ink);
  color: var(--c-paper);
  font-size: var(--fs-sm);
}

.toast.error {
  background: var(--c-danger-wash);
  color: var(--c-danger);
}

.close {
  margin-left: auto;
  border: 0;
  background: none;
  color: inherit;
  font-size: var(--fs-xs);
  text-decoration: underline;
  cursor: pointer;
}

@media (max-width: 720px) {
  .toasts {
    left: 16px;
    right: 16px;
    bottom: 16px;
  }
}
</style>
