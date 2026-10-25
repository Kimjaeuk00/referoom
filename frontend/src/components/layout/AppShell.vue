<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'
import { USE_MOCK } from '@/api/client'
import { toast } from '@/composables/useToast'
import { voiceAvailable } from '@/lib/voice'
import Icon from '@/components/common/Icon.vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
import { sideOpen } from '@/composables/useSidePanel'
import { THEMES, themePref } from '@/composables/useTheme'

const auth = useAuthStore()
const profile = useProfileStore()
const route = useRoute()
const router = useRouter()

const menu = ref(null)
const initial = computed(() => (profile.displayName || '?').slice(0, 1).toUpperCase())

onMounted(() => {
  // 새로고침 뒤에는 토큰만 남아 있으므로 최신 프로필을 다시 받는다
  if (auth.isLoggedIn && !auth.user) auth.fetchMe().catch(() => {})
})

// 메뉴에서 화면을 옮기면 메뉴를 닫는다
watch(() => route.fullPath, () => menu.value?.hidePopover?.())

// ☰: 질문하기 화면의 논문 목록을 넣었다 뺐다 한다. 다른 화면에서는 질문하기로 가서 목록을 연다.
const onAsk = computed(() => route.name === 'ask')
function toggleSide() {
  if (onAsk.value) {
    sideOpen.value = !sideOpen.value
    return
  }
  sideOpen.value = true
  router.push(auth.hasTeam ? '/ask' : '/no-team')
}

const setTheme = (key) => (themePref.value = key)

async function logout() {
  await auth.logout()
  router.replace('/login')
}

// 토큰 만료(1시간) 5분 전에 한 번 알린다. 갱신 토큰이 없어서 만료되면 다시 로그인해야 한다(DEV_02 3.1).
let expiryTimer = null
watch(
  () => auth.claims?.exp,
  (exp) => {
    clearTimeout(expiryTimer)
    if (!exp) return
    const wait = exp * 1000 - 5 * 60 * 1000 - Date.now()
    if (wait > 0) {
      expiryTimer = setTimeout(() => toast('5분 뒤 로그아웃돼요. 쓰던 질문은 복사해 두고 다시 로그인해 주세요.', { timeout: 10_000 }), wait)
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => clearTimeout(expiryTimer))
</script>

<template>
  <div class="shell">
    <header class="bar">
      <button
        type="button"
        class="icon-btn menu-btn"
        :aria-expanded="onAsk ? sideOpen : undefined"
        :aria-controls="onAsk ? 'ask-side' : undefined"
        :aria-label="onAsk && sideOpen ? '논문 목록 닫기' : '논문 목록 열기'"
        :title="onAsk && sideOpen ? '논문 목록 닫기' : '논문 목록 열기'"
        @click="toggleSide"
      >
        <Icon name="menu" />
      </button>
      <RouterLink :to="auth.hasTeam ? '/' : '/settings'" class="wordmark" aria-label="Referoom"><BrandLogo :size="26" /></RouterLink>

      <nav id="app-menu" ref="menu" popover class="menu" aria-label="주 메뉴">
        <p class="menu-who">{{ profile.displayName }} <span v-if="profile.team">{{ profile.team.name }}</span></p>
        <template v-if="auth.hasTeam">
          <RouterLink to="/" exact-active-class="router-link-active">홈</RouterLink>
          <RouterLink to="/ask">질문하기</RouterLink>
          <RouterLink to="/library">팀 라이브러리</RouterLink>
          <RouterLink v-if="voiceAvailable" to="/voice">음성 튜터</RouterLink>
        </template>
        <RouterLink to="/settings">설정</RouterLink>
        <div class="menu-theme">
          <span class="section-label">화면 모드</span>
          <div class="segmented" role="group" aria-label="화면 모드">
            <button v-for="[key, name] in THEMES" :key="key" type="button" :aria-pressed="themePref === key" @click="setTheme(key)">{{ name }}</button>
          </div>
        </div>
        <button type="button" class="menu-logout" @click="logout">로그아웃</button>
      </nav>

      <div class="tools">
        <span v-if="USE_MOCK" class="mock" title="VITE_USE_MOCK=true: 서버 대신 목업 응답을 씁니다">목업 데이터</span>
        <RouterLink v-if="auth.hasTeam" to="/library" class="icon-btn" aria-label="팀 라이브러리" title="팀 라이브러리"><Icon name="library" /></RouterLink>
        <RouterLink to="/settings" class="icon-btn" aria-label="설정" title="설정"><Icon name="settings" /></RouterLink>
        <button type="button" class="avatar" popovertarget="app-menu" :title="profile.team ? `${profile.displayName}, ${profile.team.name}` : profile.displayName">
          <span aria-hidden="true">{{ initial }}</span>
          <span class="visually-hidden">메뉴 열기: {{ profile.displayName }}</span>
        </button>
      </div>
    </header>
    <main class="main" :class="{ wide: route.meta.wide }">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.bar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: 52px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 12px 0 0;
  /* onlines 머리말처럼 반투명 흰색 */
  background: var(--c-bar);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--c-rule);
}

/* 시안처럼 메뉴 버튼은 칸막이로 나눈 왼쪽 칸에 둔다 */
.menu-btn {
  width: 52px;
  height: 52px;
  border-radius: 0;
  border-right: 1px solid var(--c-rule);
}

.wordmark {
  margin-left: 14px;
  display: inline-flex;
  text-decoration: none;
}

.menu {
  position: fixed;
  inset: 56px 12px auto auto;
  margin: 0;
  width: 220px;
  padding: 8px;
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-l);
  background: var(--c-paper);
  box-shadow: var(--shadow-float);
}

.menu:popover-open {
  display: grid;
  gap: 2px;
}

.menu-who {
  padding: 6px 10px 10px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--c-rule);
  font-size: var(--fs-sm);
  font-weight: 600;
}

.menu-who span {
  margin-left: 6px;
  font-weight: 400;
  color: var(--c-ink-muted);
}

.menu a,
.menu-logout {
  padding: 8px 10px;
  border: 0;
  border-radius: var(--radius-m);
  background: none;
  color: var(--c-ink);
  font-size: var(--fs-sm);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

.menu a:hover,
.menu-logout:hover {
  background: var(--c-surface);
}

.menu a.router-link-active {
  background: var(--c-accent-wash);
  font-weight: 600;
}

.menu-theme {
  margin-top: 6px;
  padding: 10px 10px 4px;
  border-top: 1px solid var(--c-rule);
  display: grid;
  gap: 8px;
}

.menu-theme .segmented button {
  min-height: 28px;
  padding: 0 10px;
  font-size: var(--fs-xs);
}

.menu-logout {
  margin-top: 6px;
  border-top: 1px solid var(--c-rule);
  border-radius: 0;
  color: var(--c-ink-muted);
}

.tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.mock {
  margin-right: 8px;
  padding: 1px 8px;
  border: 1px dashed var(--c-review);
  border-radius: var(--radius-s);
  color: var(--c-review);
  font-size: var(--fs-xs);
}

.tools .router-link-exact-active:not(.avatar) {
  background: var(--c-surface);
}

/* 이름 첫 글자를 넣은 동그라미 */
.avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  margin-left: 6px;
  padding: 0;
  border: 1.5px solid var(--c-ink);
  border-radius: 50%;
  background: var(--c-paper);
  color: var(--c-ink);
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}

.avatar:hover {
  background: var(--c-surface);
}

.main {
  flex: 1;
  width: 100%;
  max-width: var(--shell-w);
  margin: 0 auto;
  padding: 32px 24px 0;
}

/* 질문하기는 시안처럼 화면 전체를 쓰는 작업 공간 */
.main.wide {
  max-width: none;
  padding: 0;
}

@media (max-width: 720px) {
  .mock {
    display: none;
  }

  .main:not(.wide) {
    padding: 20px 16px 0;
  }
}
</style>
