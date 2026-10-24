<script setup>
// 직접 그린 일러스트: 논문 한 장과 돋보기. 빈 화면·찾지 못했을 때 쓴다.
defineProps({ size: { type: Number, default: 140 } })
</script>

<template>
  <svg
    class="search-illust"
    :width="size"
    :height="size"
    viewBox="0 0 160 160"
    fill="none"
    stroke="var(--illust-line)"
    stroke-width="3"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path d="M22 26l3 7 7 3-7 3-3 7-3-7-7-3 7-3z" fill="var(--c-mint)" />
    <path d="M138 30l2.5 6 6 2.5-6 2.5-2.5 6-2.5-6-6-2.5 6-2.5z" fill="var(--c-blue)" />
    <!-- 논문 -->
    <path d="M40 18h56l22 22v90a8 8 0 0 1-8 8H40a8 8 0 0 1-8-8V26a8 8 0 0 1 8-8z" fill="var(--c-paper)" />
    <path d="M96 18v22h22" fill="#f8e1e8" />
    <path d="M46 56h50M46 70h58M46 84h40" stroke-width="2.4" />
    <rect x="44" y="94" width="44" height="9" rx="3" fill="var(--c-marker)" stroke="none" opacity="0.85" />
    <path d="M46 98h40" stroke-width="2.4" />
    <!-- 돋보기 -->
    <circle cx="104" cy="104" r="22" fill="#e2eaf5" />
    <path d="M120 120l20 20" stroke-width="6" />
    <path d="M94 96a12 12 0 0 1 12-6" stroke-width="2.4" />
  </svg>
</template>

<style scoped>
.search-illust {
  --illust-line: #070606;
  max-width: 100%;
  height: auto;
}

:root[data-theme="dark"] .search-illust {
  --illust-line: #f4f2f1;
}
</style>
