<script setup>
import { VIEWS } from '@/lib/levels'

defineProps({
  view: { type: String, default: null },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:view'])
</script>

<template>
  <fieldset class="vs">
    <legend class="label">관점</legend>
    <div class="segmented">
      <button
        v-for="(info, key) in VIEWS"
        :key="key"
        type="button"
        :aria-pressed="view === key"
        :title="info.desc"
        :disabled="disabled"
        @click="$emit('update:view', key)"
      >
        {{ info.name }}
      </button>
    </div>
    <p class="hint">{{ VIEWS[view]?.desc }}</p>
  </fieldset>
</template>

<style scoped>
.vs {
  display: grid;
  gap: 8px;
}
</style>
