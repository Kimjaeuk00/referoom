<script setup>
import Icon from '@/components/common/Icon.vue'

defineEmits(['add-paper', 'ask-team'])
</script>

<template>
  <div class="callout info" role="status">
    <Icon name="forward" />
    <div>
      <p class="callout-title">팀 라이브러리에서 찾지 못했어요</p>
      <p class="text">팀이 모은 논문에는 이 질문의 근거가 없어서 답하지 않았어요. 관련 논문을 추가하거나 팀원에게 물어보세요.</p>
      <div class="actions">
        <button type="button" class="btn btn-primary" @click="$emit('add-paper')">논문 추가하기</button>
        <button type="button" class="btn" @click="$emit('ask-team')">팀원에게 질문하기</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.callout {
  max-width: 62ch;
}

.text {
  margin-top: 4px;
  color: var(--c-ink-muted);
}

.actions {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
