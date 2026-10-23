import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api/client'
import { decodeJwt, isExpired } from '@/lib/jwt'

// 토큰은 메모리(Pinia) + sessionStorage. 새로고침해도 유지되고 탭을 닫으면 사라진다(DEV_02 3.1).
const STORAGE_KEY = 'referoom.accessToken'

function readStoredToken() {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(readStoredToken())
  const user = ref(null) // 로그인 응답 또는 GET /api/me의 user

  const claims = computed(() => decodeJwt(token.value))
  const isLoggedIn = computed(() => Boolean(token.value) && !isExpired(claims.value))
  const hasTeam = computed(() => claims.value?.team_id != null)
  const isAdmin = computed(() => claims.value?.role === 'team_admin')

  function setToken(value) {
    token.value = value || null
    try {
      if (value) sessionStorage.setItem(STORAGE_KEY, value)
      else sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // 저장소를 못 쓰는 환경이면 메모리에만 둔다
    }
  }

  // 로그인·프로필 변경·팀 참여 응답은 모두 { accessToken, user } 형태다(DEV_01 4.1)
  function applySession(data) {
    if (data?.accessToken) setToken(data.accessToken)
    if (data?.user) user.value = data.user
  }

  function clear() {
    setToken(null)
    user.value = null
  }

  async function login(username, password) {
    const data = await api.auth('/api/login', {
      method: 'POST',
      json: { username, password },
      skipAuthRedirect: true,
    })
    applySession(data)
  }

  function signup(payload) {
    return api.auth('/api/signup', { method: 'POST', json: payload, skipAuthRedirect: true })
  }

  async function fetchMe() {
    const data = await api.auth('/api/me')
    user.value = data?.user ?? null
    return user.value
  }

  async function logout() {
    try {
      await api.auth('/api/logout', { method: 'POST', skipAuthRedirect: true })
    } catch {
      // 실패해도 로컬 토큰은 지운다(DEV_02 4.5)
    } finally {
      clear()
    }
  }

  return { token, user, claims, isLoggedIn, hasTeam, isAdmin, setToken, applySession, clear, login, signup, fetchMe, logout }
})
