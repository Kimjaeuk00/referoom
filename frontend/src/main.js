import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'katex/dist/katex.min.css'
import './styles/tokens.css'
import './styles/base.css'
import App from './App.vue'
import router from './router'
import { configureClient } from './api/client'
import { errorText } from './api/errors'
import { useAuthStore } from './stores/auth'
import { toast } from './composables/useToast'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

const auth = useAuthStore(pinia)

configureClient({
  getToken: () => auth.token,
  // 401: 토큰을 지우고 로그인으로. 로그인하면 원래 화면으로 돌아온다.
  onUnauthorized: () => {
    auth.clear()
    const current = router.currentRoute.value
    if (current.name !== 'login') router.push({ name: 'login', query: { redirect: current.fullPath } })
  },
  onNoTeam: () => router.push({ name: 'no-team' }),
  onForbidden: (error) => toast(errorText(error), { tone: 'error' }),
})

app.mount('#app')
