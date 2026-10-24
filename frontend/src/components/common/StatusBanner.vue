<script setup>
defineProps({
  tone: { type: String, default: 'error' }, // error | info
  message: { type: String, required: true },
  retry: { type: Boolean, default: false },
})
defineEmits(['retry'])
</script>

<template>
  <div class="banner" :class="tone" :role="tone === 'error' ? 'alert' : 'status'">
    <p>{{ message }}</p>
    <button v-if="retry" type="button" class="btn" @click="$emit('retry')">다시 시도</button>
  </div>
</template>

<style scoped>
.banner {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  border-left: 3px solid var(--c-ink-muted);
  background: var(--c-surface);
  font-size: var(--fs-sm);
}

.banner.error {
  border-left-color: var(--c-danger);
  background: var(--c-danger-wash);
}

.banner .btn {
  margin-left: auto;
}
</style>
