<script setup>
import BrandLogo from '@/components/common/BrandLogo.vue'
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { errorText } from '@/api/errors'
import { TEAM_TYPES } from '@/lib/levels'
import { toast } from '@/composables/useToast'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({
  username: '',
  password: '',
  passwordConfirm: '',
  displayName: '',
  teamMode: 'create', // create | join (DEV_01 4.1)
  teamName: '',
  teamType: 'dev',
  teamCode: '',
})
const touched = ref(false)
const busy = ref(false)
const serverError = ref('')
const createdTeam = ref(null) // 새 팀을 만들었을 때 초대 코드를 보여 준다

const errors = computed(() => {
  const e = {}
  const username = form.username.trim()
  if (username.length < 4 || username.length > 50) e.username = '아이디는 4~50자로 입력하세요.'
  if (form.password.length < 8) e.password = '비밀번호는 8자 이상이어야 해요.'
  if (form.passwordConfirm !== form.password) e.passwordConfirm = '비밀번호가 서로 달라요.'
  if (!form.displayName.trim()) e.displayName = '화면에 보일 이름을 입력하세요.'
  if (form.teamMode === 'create' && !form.teamName.trim()) e.teamName = '팀 이름을 입력하세요.'
  if (form.teamMode === 'join' && !form.teamCode.trim()) e.teamCode = '초대 코드를 입력하세요.'
  return e
})
const show = (field) => touched.value && errors.value[field]

function payload() {
  const base = {
    username: form.username.trim(),
    password: form.password,
    displayName: form.displayName.trim(),
    teamMode: form.teamMode,
  }
  return form.teamMode === 'create'
    ? { ...base, teamName: form.teamName.trim(), teamType: form.teamType }
    : { ...base, teamCode: form.teamCode.trim().toUpperCase() }
}

async function startSession() {
  try {
    await auth.login(form.username.trim(), form.password)
    router.replace('/')
  } catch {
    router.replace({ name: 'login', query: { username: form.username.trim() } })
  }
}

async function submit() {
  touched.value = true
  serverError.value = ''
  if (Object.keys(errors.value).length || busy.value) return
  busy.value = true
  try {
    const data = await auth.signup(payload())
    if (form.teamMode === 'create' && data?.inviteCode) {
      createdTeam.value = { name: form.teamName.trim(), inviteCode: data.inviteCode }
    } else {
      await startSession()
    }
  } catch (e) {
    serverError.value = errorText(e, {
      CONFLICT: '이미 쓰고 있는 아이디예요. 다른 아이디를 입력하세요.',
      VALIDATION_ERROR: '입력 형식을 다시 확인해 주세요.',
    })
  } finally {
    busy.value = false
  }
}

async function copyCode() {
  try {
    await navigator.clipboard.writeText(createdTeam.value.inviteCode)
    toast('초대 코드를 복사했어요.')
  } catch {
    toast('복사하지 못했어요. 코드를 직접 선택해 복사하세요.', { tone: 'error' })
  }
}
</script>

<template>
  <div class="auth glow-bg">
    <div class="auth-col">
      <RouterLink to="/login" class="brand-link" aria-label="Referoom"><BrandLogo :size="28" /></RouterLink>

      <template v-if="createdTeam">
        <h1>{{ createdTeam.name }} 팀을 만들었어요</h1>
        <p class="lead">팀원에게 아래 초대 코드를 알려 주세요. 가입할 때 "초대 코드로 참여"에 입력하면 같은 팀이 돼요.</p>
        <div class="code">
          <span class="code-value tabular">{{ createdTeam.inviteCode }}</span>
          <button type="button" class="btn" @click="copyCode">복사</button>
        </div>
        <button type="button" class="btn btn-primary submit" @click="startSession">Referoom 시작하기</button>
      </template>

      <template v-else>
        <h1>회원가입</h1>
        <p class="lead">한 사람은 한 팀에만 속해요. 팀을 새로 만들거나 초대 코드로 참여하세요.</p>

        <form class="form" novalidate @submit.prevent="submit">
          <div class="field">
            <label class="label" for="su-username">아이디</label>
            <input id="su-username" v-model="form.username" class="input" autocomplete="username" maxlength="50" :aria-invalid="Boolean(show('username'))" />
            <p v-if="show('username')" class="field-error">{{ errors.username }}</p>
          </div>
          <div class="row">
            <div class="field">
              <label class="label" for="su-password">비밀번호</label>
              <input id="su-password" v-model="form.password" class="input" type="password" autocomplete="new-password" :aria-invalid="Boolean(show('password'))" />
              <p v-if="show('password')" class="field-error">{{ errors.password }}</p>
            </div>
            <div class="field">
              <label class="label" for="su-password2">비밀번호 확인</label>
              <input id="su-password2" v-model="form.passwordConfirm" class="input" type="password" autocomplete="new-password" :aria-invalid="Boolean(show('passwordConfirm'))" />
              <p v-if="show('passwordConfirm')" class="field-error">{{ errors.passwordConfirm }}</p>
            </div>
          </div>
          <div class="field">
            <label class="label" for="su-name">표시 이름</label>
            <input id="su-name" v-model="form.displayName" class="input" maxlength="100" :aria-invalid="Boolean(show('displayName'))" />
            <p v-if="show('displayName')" class="field-error">{{ errors.displayName }}</p>
          </div>

          <fieldset class="team">
            <legend class="label">팀</legend>
            <div class="tabs" role="tablist">
              <button type="button" role="tab" :aria-selected="form.teamMode === 'create'" @click="form.teamMode = 'create'">새 팀 만들기</button>
              <button type="button" role="tab" :aria-selected="form.teamMode === 'join'" @click="form.teamMode = 'join'">초대 코드로 참여</button>
            </div>

            <div v-if="form.teamMode === 'create'" class="tab-panel" role="tabpanel">
              <div class="field">
                <label class="label" for="su-team">팀 이름</label>
                <input id="su-team" v-model="form.teamName" class="input" maxlength="100" :aria-invalid="Boolean(show('teamName'))" />
                <p v-if="show('teamName')" class="field-error">{{ errors.teamName }}</p>
              </div>
              <div class="types">
                <label v-for="(info, key) in TEAM_TYPES" :key="key" class="type" :class="{ on: form.teamType === key }">
                  <input v-model="form.teamType" type="radio" name="teamType" :value="key" />
                  <span class="type-name">{{ info.name }}</span>
                  <span class="hint">{{ info.desc }}</span>
                </label>
              </div>
              <p class="hint">팀을 만든 사람이 팀 관리자가 돼요. Zotero 연동과 초대 코드 관리는 관리자만 할 수 있어요.</p>
            </div>

            <div v-else class="tab-panel" role="tabpanel">
              <div class="field">
                <label class="label" for="su-code">초대 코드</label>
                <input id="su-code" v-model="form.teamCode" class="input code-input" maxlength="16" autocapitalize="characters" :aria-invalid="Boolean(show('teamCode'))" />
                <p v-if="show('teamCode')" class="field-error">{{ errors.teamCode }}</p>
                <p class="hint">팀 관리자에게 받은 8자리 코드를 입력하세요.</p>
              </div>
            </div>
          </fieldset>

          <p v-if="serverError" class="field-error" role="alert">{{ serverError }}</p>
          <button class="btn btn-primary submit" type="submit" :disabled="busy">{{ busy ? '가입하는 중' : '가입하기' }}</button>
        </form>

        <p class="switch">이미 계정이 있나요? <RouterLink to="/login">로그인</RouterLink></p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100vh;
  padding: 48px 24px;
}

.auth-col {
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
  /* 로그인 화면과 같은 흰 카드 */
  padding: 28px;
  border-radius: 24px;
  border: 1px solid var(--c-glass-line);
  background: var(--c-glass-strong);
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow-float);
}

.brand-link {
  display: inline-flex;
  text-decoration: none;
}

h1 {
  margin-top: 24px;
  font-size: var(--fs-2xl);
}

.lead {
  margin-top: 8px;
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
}

.form {
  margin-top: 28px;
  display: grid;
  gap: 20px;
}

.row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.team {
  display: grid;
  gap: 12px;
}

.tabs {
  display: flex;
  border-bottom: 1px solid var(--c-rule);
}

.tabs button {
  padding: 8px 14px;
  border: 0;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  background: none;
  color: var(--c-ink-muted);
  font-size: var(--fs-sm);
  font-weight: 500;
  cursor: pointer;
}

.tabs button[aria-selected="true"] {
  color: var(--c-ink);
  border-bottom-color: var(--c-accent);
}

.tab-panel {
  display: grid;
  gap: 12px;
}

.types {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.type {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 8px;
  align-items: start;
  padding: 10px 12px;
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-m);
  background: var(--c-surface);
  cursor: pointer;
}

.type.on {
  border-color: var(--c-accent);
  box-shadow: inset 0 0 0 1px var(--c-accent);
}

.type input {
  margin-top: 5px;
  accent-color: var(--c-accent);
}

.type-name {
  font-size: var(--fs-sm);
  font-weight: 600;
}

.type .hint {
  grid-column: 2;
}

.code-input {
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.code {
  margin: 24px 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px dashed var(--c-accent);
  border-radius: var(--radius-m);
  background: var(--c-surface);
}

.code-value {
  font-size: var(--fs-2xl);
  font-weight: 600;
  letter-spacing: 0.12em;
}

.code .btn {
  margin-left: auto;
}

.submit {
  min-height: 42px;
}

.switch {
  margin-top: 24px;
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}

@media (max-width: 560px) {
  .row,
  .types {
    grid-template-columns: 1fr;
  }
}
</style>
