<script setup>
// 화면에 쓰는 선 아이콘. 라이브러리를 더 들이지 않으려고 필요한 것만 직접 그렸다(24×24, 선 1.6).
const PATHS = {
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  library: ['M5 4h4v16H5z', 'M11 4h4v16h-4z', 'M17.2 5.2l3.3-.9 3 14.6-3.3.9z'],
  settings: ['M4 7h9', 'M17 7h3', 'M15 5v4', 'M4 17h3', 'M11 17h9', 'M9 15v4'],
  doc: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5'],
  topic: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z', 'M14 3v5h5', 'M11.5 12a2.5 2.5 0 1 1 0 5 2.5 2.5 0 1 1 0-5', 'M13.4 16.4l1.8 1.8'],
  clip: ['M21 11.3l-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9'],
  search: ['M11 4a7 7 0 1 1 0 14 7 7 0 1 1 0-14', 'M20 20l-4-4'],
  upload: ['M12 15V4', 'M7 9l5-5 5 5', 'M5 20h14'],
  alert: ['M10.3 4 2.2 18a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0z', 'M12 9.5v4', 'M12 17h.01'],
  forward: ['M15 10l5 5-5 5', 'M4 4v7a4 4 0 0 0 4 4h12'],
  mic: ['M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3', 'M5.5 11a6.5 6.5 0 0 0 13 0', 'M12 17.5V21'],
  send: ['M12 19V5', 'M5.5 11.5 12 5l6.5 6.5'],
  bookmark: ['M6.5 3h11v18l-5.5-4-5.5 4z'],
  plus: ['M12 5v14', 'M5 12h14'],
  trash: ['M4 7h16', 'M10 11v6', 'M14 11v6', 'M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12', 'M9 7V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V7'],
  copy: ['M9 8h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z', 'M5 15H4.5A1.5 1.5 0 0 1 3 13.5v-9A1.5 1.5 0 0 1 4.5 3h9A1.5 1.5 0 0 1 15 4.5V5'],
  chevron: ['M6 9l6 6 6-6'],
}

defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 20 },
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="d in PATHS[name]" :key="d" :d="d" />
  </svg>
</template>
