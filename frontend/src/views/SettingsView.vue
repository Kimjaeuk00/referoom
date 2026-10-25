<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import { errorText } from '@/api/errors'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'
import { toast } from '@/composables/useToast'
import { formatDateTime } from '@/lib/format'
import { TEAM_TYPES } from '@/lib/levels'
import ViewSelector from '@/components/common/ViewSelector.vue'

const auth = useAuthStore()
const profile = useProfileStore()
const router = useRouter()

// 프로필: 저장하면 응답의 새 토큰으로 바꿔야 AI 서비스에 반영된다(DEV_02 4.5).
// PATCH /api/me/profile에는 view만 보낸다(level은 서버에 남아 있지만 v0.2에서는 화면에서 다루지 않는다). 표시 이름은 가입할 때 정한 값을 보여 주기만 한다.
const form = reactive({ view: profile.view })
const saving = ref(false)
const profileError = ref('')
watch(
  () => profile.view,
  (view) => (form.view = view),
)

async function saveProfile() {
  saving.value = true
  profileError.value = ''
  try {
    await profile.updateProfile({ view: form.view })
    toast('프로필을 저장했어요. 다음 질문부터 반영돼요.')
  } catch (e) {
    profileError.value = errorText(e)
  } finally {
    saving.value = false
  }
}

// 팀 정보: GET /api/team(백엔드 P1). 아직 없으면 로그인 응답의 team을 보여 준다.
const team = ref(null)
async function loadTeam() {
  try {
    const data = await api.auth('/api/team')
    team.value = data?.team ?? null
  } catch {
    team.value = profile.team
  }
}

async function copyInvite() {
  try {
    await navigator.clipboard.writeText(team.value.inviteCode)
    toast('초대 코드를 복사했어요.')
  } catch {
    toast('복사하지 못했어요. 코드를 직접 선택해 복사하세요.', { tone: 'error' })
  }
}

// Zotero(관리자): 연결 설정(그룹 ID·API Key)은 서버의 .env로만 관리한다. 여기서는 연결 상태만 보여 준다.
const zotero = ref(null)

async function loadZotero() {
  try {
    zotero.value = await api.rag('/zotero/config')
  } catch {
    zotero.value = null
  }
}

async function logout() {
  await auth.logout()
  router.replace('/login')
}

onMounted(() => {
  if (!auth.hasTeam) return
  loadTeam()
  if (auth.isAdmin) loadZotero()
})
</script>

<template>
  <div class="settings">
    <h1>설정</h1>

    <section class="block" aria-labelledby="s-profile">
      <h2 id="s-profile">내 프로필</h2>
      <form class="form" @submit.prevent="saveProfile">
        <dl class="facts">
          <div><dt>표시 이름</dt><dd>{{ profile.displayName }}</dd></div>
          <div><dt>아이디</dt><dd>{{ auth.user?.username ?? auth.claims?.username }}</dd></div>
        </dl>
        <ViewSelector v-model:view="form.view" />
        <p v-if="profileError" class="field-error" role="alert">{{ profileError }}</p>
        <div><button class="btn btn-primary" type="submit" :disabled="saving">{{ saving ? '저장하는 중' : '프로필 저장' }}</button></div>
      </form>
    </section>

    <section v-if="auth.hasTeam" class="block" aria-labelledby="s-team">
      <h2 id="s-team">팀</h2>
      <dl v-if="team" class="facts">
        <div><dt>팀 이름</dt><dd>{{ team.name }}</dd></div>
        <div><dt>유형</dt><dd>{{ TEAM_TYPES[team.type]?.name ?? team.type }}</dd></div>
        <div v-if="team.memberCount != null"><dt>팀원</dt><dd class="tabular">{{ team.memberCount }}명</dd></div>
        <div><dt>내 역할</dt><dd>{{ auth.isAdmin ? '팀 관리자' : '팀원' }}</dd></div>
      </dl>
      <p v-else class="hint">팀 정보를 불러오는 중이에요.</p>
      <div v-if="auth.isAdmin && team?.inviteCode" class="invite">
        <span class="label">초대 코드</span>
        <span class="code tabular">{{ team.inviteCode }}</span>
        <button type="button" class="btn" @click="copyInvite">복사</button>
      </div>
    </section>

    <section v-if="auth.isAdmin" class="block" aria-labelledby="s-zotero">
      <h2 id="s-zotero">Zotero 연결</h2>
      <p v-if="zotero?.group_id != null" class="state">
        그룹 {{ zotero.group_id }}에 연결됨 <span class="hint">마지막 동기화 {{ formatDateTime(zotero.last_synced_at) }}</span>
      </p>
      <p v-else-if="zotero" class="state">연결되지 않았어요.</p>
      <p v-else class="hint">연결 상태를 불러오지 못했어요.</p>
      <p class="hint">Zotero 그룹과 API Key는 서버 설정(.env)에서 관리해요. 바꾸려면 서버 담당자에게 요청하세요. 동기화는 팀 라이브러리 화면에서 해요.</p>
    </section>

    <section class="block" aria-labelledby="s-account">
      <h2 id="s-account">계정</h2>
      <button type="button" class="btn" @click="logout">로그아웃</button>
    </section>
  </div>
</template>

<style scoped>
.settings {
  max-width: 720px;
  margin: 0 auto;
  padding-bottom: 48px;
}

h1 {
  font-size: var(--fs-2xl);
}

.block {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--c-rule);
  display: grid;
  gap: 14px;
}

h2 {
  font-size: var(--fs-lg);
}

.form {
  display: grid;
  gap: 18px;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.facts {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 32px;
  font-size: var(--fs-sm);
}

.facts dt {
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

.facts dd {
  margin: 0;
}

.invite {
  display: flex;
  align-items: center;
  gap: 12px;
}

.code {
  font-size: var(--fs-lg);
  font-weight: 600;
  letter-spacing: 0.12em;
}

.state {
  font-size: var(--fs-sm);
}

.state .hint {
  margin-left: 6px;
}

.actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 560px) {
  .row {
    grid-template-columns: 1fr;
  }
}
</style>
