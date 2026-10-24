<script setup>
import { RouterView } from 'vue-router'
import AppShell from '@/components/layout/AppShell.vue'
import ToastHost from '@/components/common/ToastHost.vue'
</script>

<template>
  <RouterView v-slot="{ Component, route }">
    <component :is="Component" v-if="route.meta.shell === false" />
    <AppShell v-else>
      <component :is="Component" />
    </AppShell>
  </RouterView>
  <ToastHost />
</template>
