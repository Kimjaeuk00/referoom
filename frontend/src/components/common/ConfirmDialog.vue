<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  message: { type: String, default: '' },
  confirmLabel: { type: String, default: '확인' },
  danger: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])
const dialog = ref(null)

watch(
  () => props.open,
  (open) => {
    if (open && !dialog.value?.open) dialog.value?.showModal()
    if (!open && dialog.value?.open) dialog.value.close()
  },
)
</script>

<template>
  <dialog ref="dialog" class="confirm" @cancel.prevent="emit('cancel')">
    <form method="dialog" @submit.prevent="emit('confirm')">
      <h2>{{ title }}</h2>
      <p v-if="message" class="msg">{{ message }}</p>
      <div class="actions">
        <button type="button" class="btn" :disabled="busy" @click="emit('cancel')">취소</button>
        <button type="submit" class="btn" :class="danger ? 'btn-danger' : 'btn-primary'" :disabled="busy">{{ confirmLabel }}</button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.confirm {
  width: min(440px, calc(100vw - 32px));
}

form {
  padding: 24px;
  display: grid;
  gap: 12px;
}

h2 {
  font-size: var(--fs-lg);
}

.msg {
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
}

.actions {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
