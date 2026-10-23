<script setup>
// 시안처럼 화면 여기저기 흩어진 작은 장식(별, 물결선, 캡슐). 자리 잡는 건 부모가 position으로 정한다.
defineProps({ kind: { type: String, required: true } }) // star | wave | pill | spark
</script>

<template>
  <svg v-if="kind === 'star'" class="doodle" width="26" height="26" viewBox="0 0 26 26" aria-hidden="true" focusable="false">
    <path d="M13 1l3 9 9 3-9 3-3 9-3-9-9-3 9-3z" fill="var(--c-blue)" />
  </svg>
  <svg v-else-if="kind === 'spark'" class="doodle" width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" focusable="false">
    <path d="M11 1l2.4 7.6L21 11l-7.6 2.4L11 21l-2.4-7.6L1 11l7.6-2.4z" fill="var(--c-mint)" />
  </svg>
  <svg v-else-if="kind === 'wave'" class="doodle" width="40" height="18" viewBox="0 0 40 18" fill="none" aria-hidden="true" focusable="false">
    <path d="M2 12c4-8 8-8 12 0s8 8 12 0 8-8 12 0" stroke="#e07a52" stroke-width="2.6" stroke-linecap="round" />
  </svg>
  <svg v-else-if="kind === 'pill'" class="doodle" width="34" height="18" viewBox="0 0 34 18" aria-hidden="true" focusable="false">
    <rect x="1" y="1" width="32" height="16" rx="8" fill="#f9d5df" />
    <rect x="17" y="1" width="16" height="16" rx="8" fill="#f2b27a" />
  </svg>
</template>

<style scoped>
.doodle {
  pointer-events: none;
}
</style>
