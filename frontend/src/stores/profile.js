import { defineStore } from 'pinia'
import { computed } from 'vue'
import { api } from '@/api/client'
import { useAuthStore } from './auth'

// 화면에서 쓰는 내 정보. 값은 GET /api/me(최신) → 없으면 토큰 claim 순으로 읽는다.
export const useProfileStore = defineStore('profile', () => {
  const auth = useAuthStore()

  const displayName = computed(() => auth.user?.displayName || auth.claims?.username || '')
  const team = computed(() => auth.user?.team ?? null)

  // 지금은 바꿀 프로필 항목이 없다(수준·관점 제거). 서버는 본문을 읽지 않고 새 토큰만 발급한다.
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

  return { displayName, team, updateProfile, joinTeam }
})
