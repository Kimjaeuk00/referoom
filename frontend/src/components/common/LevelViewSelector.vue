<script setup>
import { LEVEL_ORDER, LEVELS, VIEWS } from '@/lib/levels'

defineProps({
  level: { type: String, required: true },
  view: { type: String, default: null },
  showView: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
})
defineEmits(['update:level', 'update:view'])
</script>

<template>
  <div class="lv">
    <fieldset>
      <legend class="label">설명 수준</legend>
      <div class="segmented">
        <button
          v-for="key in LEVEL_ORDER"
          :key="key"
          type="button"
          :aria-pressed="level === key"
          :title="LEVELS[key].desc"
          :disabled="disabled"
          @click="$emit('update:level', key)"
        >
          {{ key }} {{ LEVELS[key].name }}
        </button>
      </div>
      <p class="hint">{{ LEVELS[level]?.desc }}</p>
    </fieldset>

    <fieldset v-if="showView">
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
  </div>
</template>

<style scoped>
.lv {
  display: grid;
  gap: 20px;
}

fieldset {
  display: grid;
  gap: 8px;
}
</style>
