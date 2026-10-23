<script setup>
// 직접 그린 일러스트: 세 사람이 펼친 논문 한 편을 함께 본다(굵은 검정 선 + 파스텔 채움).
// 색은 토큰을 써서 다크 모드에서도 같이 바뀐다. 장식용이라 화면 낭독기에는 숨긴다.
defineProps({ size: { type: Number, default: 320 } })
</script>

<template>
  <svg
    class="readers"
    :width="size"
    :height="size * 0.86"
    viewBox="0 0 360 310"
    fill="none"
    stroke="var(--illust-line)"
    stroke-width="3"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <!-- 반짝이 -->
    <path d="M40 60l4 10 10 4-10 4-4 10-4-10-10-4 10-4z" fill="var(--c-mint)" />
    <path d="M318 46l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" fill="var(--c-blue)" />
    <path d="M330 170l2.5 6 6 2.5-6 2.5-2.5 6-2.5-6-6-2.5 6-2.5z" fill="#f2b27a" />

    <!-- 왼쪽 사람(민트 옷, 단발) -->
    <path d="M30 300c0-62 22-96 70-98 48 2 66 36 66 98" fill="#bfeedd" />
    <circle cx="98" cy="150" r="34" fill="#f7d6c1" />
    <path d="M64 148c-2-30 18-48 40-46 24 2 34 22 30 40-12-4-24-14-28-26-8 14-24 26-42 32z" fill="var(--illust-hair)" />
    <circle cx="88" cy="156" r="2.6" fill="var(--illust-line)" stroke="none" />
    <circle cx="110" cy="156" r="2.6" fill="var(--illust-line)" stroke="none" />
    <path d="M92 168c4 4 10 4 14 0" />
    <circle cx="80" cy="166" r="5" fill="#f4a9b8" stroke="none" opacity="0.8" />
    <circle cx="118" cy="166" r="5" fill="#f4a9b8" stroke="none" opacity="0.8" />

    <!-- 가운데 사람(복숭아 옷, 둥근 머리) -->
    <path d="M118 300c0-70 24-112 64-114 42 2 62 44 62 114" fill="#fde0c8" />
    <circle cx="182" cy="112" r="38" fill="#f1c6a4" />
    <path d="M144 110c-6-34 22-56 48-50 26 6 34 30 28 46-6-12-20-22-38-22-14 0-26 10-38 26z" fill="#c9b8f0" />
    <circle cx="198" cy="64" r="14" fill="#c9b8f0" />
    <circle cx="170" cy="120" r="2.8" fill="var(--illust-line)" stroke="none" />
    <circle cx="194" cy="120" r="2.8" fill="var(--illust-line)" stroke="none" />
    <path d="M174 134c5 5 12 5 17 0" />
    <circle cx="161" cy="131" r="5.5" fill="#f4a9b8" stroke="none" opacity="0.8" />
    <circle cx="204" cy="131" r="5.5" fill="#f4a9b8" stroke="none" opacity="0.8" />

    <!-- 오른쪽 사람(파랑 옷, 짧은 머리, 안경) -->
    <path d="M206 300c0-60 20-94 64-96 44 2 62 36 62 96" fill="#c8d7f3" />
    <circle cx="268" cy="152" r="32" fill="#d9a07a" />
    <path d="M236 146c0-26 16-40 34-40 20 0 34 14 32 38-10-10-22-14-34-14-12 0-22 6-32 16z" fill="var(--illust-hair)" />
    <circle cx="257" cy="157" r="8" fill="none" />
    <circle cx="280" cy="157" r="8" fill="none" />
    <path d="M265 157h7" />
    <path d="M262 172c4 3 9 3 13 0" />

    <!-- 펼친 논문: 왼쪽·오른쪽 쪽, 가운데 접힌 선 -->
    <path d="M62 230c40-12 78-10 118 6v70c-40-14-78-16-118-4z" fill="var(--c-paper)" />
    <path d="M298 230c-40-12-78-10-118 6v70c40-14 78-16 118-4z" fill="var(--c-paper)" />
    <!-- 왼쪽 쪽 글줄, 그중 한 줄은 형광펜 -->
    <path d="M80 248c26-6 52-5 82 4" stroke-width="2.4" />
    <rect x="78" y="258" width="72" height="9" rx="3" fill="var(--c-marker)" stroke="none" opacity="0.85" transform="rotate(4 114 262)" />
    <path d="M80 262c26-6 52-5 82 4" stroke-width="2.4" />
    <path d="M80 276c22-5 44-4 66 3" stroke-width="2.4" />
    <!-- 오른쪽 쪽: 출처 표시 알약 두 개 -->
    <rect x="198" y="246" width="30" height="14" rx="7" fill="#dcf3ea" stroke-width="2.2" />
    <rect x="234" y="250" width="30" height="14" rx="7" fill="#e2eaf5" stroke-width="2.2" />
    <path d="M198 274c26-5 52-6 82-2" stroke-width="2.4" />
    <path d="M198 288c22-4 44-5 66-2" stroke-width="2.4" />

    <!-- 책을 잡은 손 -->
    <circle cx="66" cy="262" r="11" fill="#f7d6c1" />
    <circle cx="294" cy="262" r="11" fill="#d9a07a" />
  </svg>
</template>

<style scoped>
.readers {
  --illust-line: #070606;
  --illust-hair: #2b2523;
  max-width: 100%;
  height: auto;
}

:root[data-theme="dark"] .readers {
  --illust-line: #f4f2f1;
  --illust-hair: #3b3432;
}
</style>
