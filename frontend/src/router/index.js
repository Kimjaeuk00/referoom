import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { voiceAvailable } from '@/lib/voice'

const routes = [
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { team: true, wide: true } },
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { guest: true, shell: false } },
  { path: '/signup', name: 'signup', component: () => import('@/views/SignupView.vue'), meta: { guest: true, shell: false } },
  { path: '/ask', name: 'ask', component: () => import('@/views/AskView.vue'), meta: { team: true, wide: true } },
  { path: '/library', name: 'library', component: () => import('@/views/LibraryView.vue'), meta: { team: true } },
  { path: '/papers/:id', name: 'paper', component: () => import('@/views/PaperDetailView.vue'), meta: { team: true } },
  ...(voiceAvailable ? [{ path: '/voice', name: 'voice', component: () => import('@/views/VoiceTutorView.vue'), meta: { team: true } }] : []),
  { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
  { path: '/no-team', name: 'no-team', component: () => import('@/views/NoTeamView.vue') },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// 라우트 가드(DEV_02 3.3)
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.guest) return auth.isLoggedIn ? { name: 'home' } : true
  if (!auth.isLoggedIn) {
    auth.clear()
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.team && !auth.hasTeam) return { name: 'no-team' }
  if (to.name === 'no-team' && auth.hasTeam) return { name: 'home' }
  return true
})

export default router
