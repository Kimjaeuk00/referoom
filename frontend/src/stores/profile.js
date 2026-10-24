import { defineStore } from 'pinia'
import { computed } from 'vue'
import { api } from '@/api/client'
import { useAuthStore } from './auth'

// 화면에서 쓰는 내 정보. 값은 GET /api/me(최신) → 없으면 토큰 claim 순으로 읽는다.
export const useProfileStore = defineStore('profile', () => {
  const auth = useAuthStore()

  const level = computed(() => auth.user?.level ?? auth.claims?.level ?? 'L2')
  const view = computed(() => auth.user?.view ?? auth.claims?.view ?? 'dev')
  const displayName = computed(() => auth.user?.displayName || auth.claims?.username || '')
  const team = computed(() => auth.user?.team ?? null)

  // 수준·관점을 바꾸면 응답의 새 토큰으로 바꿔야 AI 서비스에 반영된다(DEV_01 4.1)
  async function updateProfile(changes) {
    const data = await api.auth('/api/me/profile', { method: 'PATCH', json: changes })
    auth.applySession(data)
    return data
  }

  async function joinTeam(teamCode) {
    const data = await api.auth('/api/team/join', { method: 'POST', json: { teamCode } })
    auth.applySession(data)
    return data
  }

  return { level, view, displayName, team, updateProfile, joinTeam }
})
