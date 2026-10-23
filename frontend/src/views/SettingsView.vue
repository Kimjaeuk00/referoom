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
import LevelViewSelector from '@/components/common/LevelViewSelector.vue'

const auth = useAuthStore()
const profile = useProfileStore()
const router = useRouter()

// 프로필: 저장하면 응답의 새 토큰으로 바꿔야 AI 서비스에 반영된다(DEV_02 4.5).
// PATCH /api/me/profile은 level·view만 받는다(DEV_01 4.5). 표시 이름은 가입할 때 정한 값을 보여 주기만 한다.
const form = reactive({ level: profile.level, view: profile.view })
const saving = ref(false)
const profileError = ref('')
watch(
  () => [profile.level, profile.view],
  ([level, view]) => Object.assign(form, { level, view }),
)

async function saveProfile() {
  saving.value = true
  profileError.value = ''
  try {
    await profile.updateProfile({ level: form.level, view: form.view })
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

// Zotero(관리자): 저장한 키는 다시 보여 주지 않는다. 입력칸은 항상 비워 둔다.
const zotero = ref(null)
const zForm = reactive({ groupId: '', apiKey: '' })
const zBusy = ref(false)
const zError = ref('')

async function loadZotero() {
  try {
    zotero.value = await api.rag('/zotero/config')
  } catch {
    zotero.value = null
  }
}

async function saveZotero() {
  zError.value = ''
  const groupId = Number(zForm.groupId.trim())
  if (!zForm.groupId.trim() || !zForm.apiKey.trim()) {
    zError.value = '그룹 ID와 API Key를 모두 입력하세요.'
    return
  }
  if (!Number.isInteger(groupId) || groupId <= 0) {
    zError.value = '그룹 ID는 숫자예요. Zotero 그룹 주소의 groups/ 뒤 숫자를 넣으세요.'
    return
  }
  zBusy.value = true
  try {
    await api.rag('/zotero/config', { method: 'POST', json: { group_id: groupId, api_key: zForm.apiKey.trim() } })
    toast('Zotero 연결을 확인하고 저장했어요.')
    await loadZotero()
  } catch (e) {
    zError.value = errorText(e)
  } finally {
    zForm.apiKey = ''
    zBusy.value = false
  }
}

async function disconnectZotero() {
  zBusy.value = true
  zError.value = ''
  try {
    await api.rag('/zotero/config', { method: 'DELETE' })
    toast('Zotero 연결을 해제했어요.')
    await loadZotero()
  } catch (e) {
    zError.value = errorText(e)
  } finally {
    zBusy.value = false
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
        <LevelViewSelector v-model:level="form.level" v-model:view="form.view" />
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
      <p class="hint">팀 Zotero 그룹 라이브러리를 연결하면 라이브러리 화면에서 동기화할 수 있어요. 저장한 API Key는 다시 보여 주지 않아요.</p>
      <p v-if="zotero?.group_id != null" class="state">
        그룹 {{ zotero.group_id }}에 연결됨 <span class="hint">마지막 동기화 {{ formatDateTime(zotero.last_synced_at) }}</span>
      </p>
      <form class="form" autocomplete="off" @submit.prevent="saveZotero">
        <div class="row">
          <div class="field">
            <label class="label" for="z-group">그룹 ID</label>
            <input id="z-group" v-model="zForm.groupId" class="input" inputmode="numeric" />
          </div>
          <div class="field">
            <label class="label" for="z-key">API Key</label>
            <input id="z-key" v-model="zForm.apiKey" class="input" type="password" autocomplete="new-password" :placeholder="zotero?.group_id != null ? '등록됨 (바꾸려면 새로 입력)' : ''" />
          </div>
        </div>
        <p v-if="zError" class="field-error" role="alert">{{ zError }}</p>
        <div class="actions">
          <button class="btn btn-primary" type="submit" :disabled="zBusy">{{ zBusy ? '확인하는 중' : '연결 확인 후 저장' }}</button>
          <button v-if="zotero?.group_id != null" type="button" class="btn btn-danger" :disabled="zBusy" @click="disconnectZotero">연결 해제</button>
        </div>
      </form>
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
