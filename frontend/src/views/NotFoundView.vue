<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <section class="nf">
    <h1>찾는 화면이 없어요</h1>
    <p class="lead">주소가 바뀌었거나 잘못 입력됐을 수 있어요.</p>
    <RouterLink to="/ask" class="btn btn-primary">질문하기로 가기</RouterLink>
  </section>
</template>

<style scoped>
.nf {
  padding-top: 24px;
  display: grid;
  gap: 12px;
  justify-items: start;
}

h1 {
  font-size: var(--fs-2xl);
}

.lead {
  color: var(--c-ink-muted);
}

.btn {
  text-decoration: none;
}
</style>
