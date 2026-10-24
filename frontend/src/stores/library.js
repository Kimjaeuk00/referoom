import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api/client'

// 여러 화면이 함께 쓰는 라이브러리 요약: 상단 통계와 범위 선택용 논문 목록
export const useLibraryStore = defineStore('library', () => {
  const stats = ref(null)
  const allPapers = ref([])

  const tags = computed(() => [...new Set(allPapers.value.flatMap((p) => p.tags ?? []))].sort())
  const isEmpty = computed(() => stats.value != null && stats.value.papers === 0)

  async function loadStats() {
    stats.value = await api.rag('/library/stats')
  }

  async function loadAllPapers() {
    const data = await api.rag('/papers', { query: { status: 'indexed', page: 1, size: 200 } })
    allPapers.value = data?.items ?? []
  }

  function refresh() {
    return Promise.allSettled([loadStats(), loadAllPapers()])
  }

  return { stats, allPapers, tags, isEmpty, loadStats, loadAllPapers, refresh }
})
