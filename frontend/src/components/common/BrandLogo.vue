<script setup>
// Referoom 로고: "참고(reference) + 방(room)". 둥근 네모 방 안에 펼친 논문, 오른쪽 쪽에 복숭아색 책갈피.
// 16px 파비콘에서도 알아보게 도형을 적게 썼다. markOnly면 마크만 그린다.
defineProps({
  size: { type: Number, default: 28 },
  markOnly: { type: Boolean, default: false },
})
</script>

<template>
  <span class="brand" :class="{ 'mark-only': markOnly }">
    <svg :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" fill="var(--logo-room)" />
      <path d="M6 10.5c3.4-1.8 6.8-1.8 10 0V24c-3.2-1.8-6.6-1.8-10 0z" fill="var(--logo-page)" />
      <path d="M26 10.5c-3.4-1.8-6.8-1.8-10 0V24c3.2-1.8 6.6-1.8 10 0z" fill="var(--logo-page)" />
      <path d="M20.5 8.5h3.5v8l-1.75-1.4-1.75 1.4z" fill="var(--logo-ribbon)" />
    </svg>
    <span v-if="!markOnly" class="name">Referoom</span>
  </span>
</template>

<style scoped>
.brand {
  --logo-room: #5f8a5b;
  --logo-page: #fffdfb;
  --logo-ribbon: #f0a57e;
  display: inline-flex;
  align-items: center;
  gap: 9px;
}

.name {
  font-family: var(--font);
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--c-ink);
}

:root[data-theme="dark"] .brand {
  --logo-room: #7fae7a;
  --logo-page: #f6f2ec;
  --logo-ribbon: #f0a57e;
}
</style>
