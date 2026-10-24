<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProfileStore } from '@/stores/profile'
import { errorText } from '@/api/errors'

const auth = useAuthStore()
const profile = useProfileStore()
const router = useRouter()

const code = ref('')
const busy = ref(false)
const error = ref('')

async function join() {
  error.value = ''
  if (!code.value.trim()) {
    error.value = '초대 코드를 입력하세요.'
    return
  }
  busy.value = true
  try {
    await profile.joinTeam(code.value.trim().toUpperCase())
    router.replace('/')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

async function logout() {
  await auth.logout()
  router.replace('/login')
}
</script>

<template>
  <section class="no-team">
    <h1>팀에 참여해 주세요</h1>
    <p class="lead">질문과 라이브러리는 팀 단위로 쓰여요. 팀 관리자에게 받은 초대 코드를 입력하면 바로 시작할 수 있어요.</p>

    <form class="form" novalidate @submit.prevent="join">
      <div class="field">
        <label class="label" for="invite">초대 코드</label>
        <div class="inline">
          <input id="invite" v-model="code" class="input code-input" maxlength="16" autocapitalize="characters" :aria-invalid="Boolean(error)" />
          <button class="btn btn-primary" type="submit" :disabled="busy">{{ busy ? '참여하는 중' : '팀에 참여' }}</button>
        </div>
        <p v-if="error" class="field-error" role="alert">{{ error }}</p>
      </div>
    </form>

    <p class="other">다른 계정으로 쓰려면 <button type="button" class="btn-quiet link" @click="logout">로그아웃</button>하세요.</p>
  </section>
</template>

<style scoped>
.no-team {
  max-width: 520px;
  padding-top: 24px;
}

h1 {
  font-size: var(--fs-2xl);
}

.lead {
  margin-top: 8px;
  color: var(--c-ink-muted);
}

.form {
  margin-top: 28px;
}

.inline {
  display: flex;
  gap: 8px;
}

.code-input {
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.other {
  margin-top: 32px;
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}

.link {
  padding: 0;
  border: 0;
  background: none;
  color: var(--c-accent);
  text-decoration: underline;
  cursor: pointer;
}
</style>
