<script setup>
import SearchIllust from '@/components/illust/SearchIllust.vue'

defineProps({
  title: { type: String, required: true },
  text: { type: String, default: '' },
})
</script>

<template>
  <div class="empty">
    <SearchIllust :size="120" class="art" />
    <div>
      <p class="title">{{ title }}</p>
      <p v-if="text" class="text">{{ text }}</p>
      <div class="actions"><slot /></div>
    </div>
  </div>
</template>

<style scoped>
.empty {
  padding: 40px 0;
  max-width: 620px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 24px;
}

.title {
  font-family: var(--font-display);
  font-size: var(--fs-xl);
  font-weight: 600;
}

.text {
  margin-top: 6px;
  color: var(--c-ink-muted);
}

.actions {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.actions:empty {
  display: none;
}

@media (max-width: 560px) {
  .empty {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
