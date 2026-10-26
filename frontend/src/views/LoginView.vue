<script setup>
import { reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { errorText } from '@/api/errors'
import BrandLogo from '@/components/common/BrandLogo.vue'
import Icon from '@/components/common/Icon.vue'
import ReadersIllust from '@/components/illust/ReadersIllust.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const form = reactive({ username: String(route.query.username ?? ''), password: '' })
const busy = ref(false)
const error = ref('')

// 시안의 "What Bothers You?" 카드: 논문을 읽다 막히는 지점과 Referoom이 돕는 방식
const PAINS = [
  { icon: 'term', title: '용어가 낯설어요', text: '답변 아래 "더 쉽게"를 누르면 비유와 쉬운 말로 다시 풀어 설명해요.' },
  { icon: 'formula', title: '수식이 어려워요', text: '수식은 그대로 보여 주고, 원문에서 확인할 쪽을 알려 줘요.' },
  { icon: 'source', title: '근거가 궁금해요', text: '답마다 어느 논문 몇 쪽에서 왔는지 붙어요.' },
  { icon: 'code', title: '구현할 때 막혀요', text: '구현 관점을 고르면 입출력, 설정값, 주의점 위주로 답해요.' },
]

// 시안의 "How does the first session go?" 단계
const STEPS = [
  { title: '논문 모으기', text: 'PDF를 올리거나 Zotero 그룹을 연결하거나, 주제로 arXiv에서 찾아 팀 라이브러리에 모아요.' },
  { title: '질문하기', text: '관점(구현, 연구)을 고르고 물어보세요. 어려우면 "더 쉽게", 더 알고 싶으면 "더 깊게"를 눌러요.' },
  { title: '논문 쓰기 돕기', text: '입력창 아래 선행연구·주제·검증 중 하나를 켜면 정리표, 연구 주제 후보, 원고 수치 대조를 받아요. 아무것도 켜지 않으면 일반 질문이에요.' },
  { title: '근거 확인', text: '답 속 출처 표시를 누르면 논문과 쪽수, 근거 문장이 보여요.' },
]
const step = ref(0)

// 시안의 "Questions and answers"
const FAQ = [
  { q: '라이브러리에 없는 내용을 물으면 어떻게 되나요?', a: '지어내서 답하지 않아요. 찾지 못했다고 알려 주고, 관련 논문을 추가하거나 팀원에게 물어보도록 안내해요.' },
  { q: '답이 틀릴 수도 있나요?', a: '수식이나 수치가 들어간 답은 근거 상자에 원문 확인 안내가 붙어요. 출처의 쪽수로 원문을 꼭 대조해 보세요.' },
  { q: '팀원은 어떻게 초대하나요?', a: '팀을 만들면 초대 코드가 나와요. 팀원이 가입할 때 그 코드를 넣으면 같은 팀이 돼요.' },
  { q: 'Zotero 연동은 어떻게 하나요?', a: '서버 설정에 Zotero 그룹이 연결돼 있어요. 설정 화면에서 연결 상태를 확인하고 지금 동기화할 수 있어요.' },
  { q: '원고를 넣으면 어디로 가나요?', a: '검증 모드에서 원고는 외부 LLM으로 전송돼요. 처음 보낼 때 안내가 나오고, 로그와 색인에는 저장하지 않아요.' },
]

// 로그인 후 원래 화면으로 돌아간다. 외부 주소로는 보내지 않는다.
function nextPath() {
  const r = route.query.redirect
  return typeof r === 'string' && r.startsWith('/') && !r.startsWith('//') ? r : '/'
}

async function submit() {
  if (busy.value) return
  error.value = ''
  if (!form.username.trim() || !form.password) {
    error.value = '아이디와 비밀번호를 입력하세요.'
    return
  }
  busy.value = true
  try {
    await auth.login(form.username.trim(), form.password)
    router.replace(nextPath())
  } catch (e) {
    // 계정이 있는지 없는지는 구분해서 알려 주지 않는다
    error.value = errorText(e, { UNAUTHORIZED: '아이디 또는 비밀번호가 올바르지 않아요' })
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="landing">
    <div class="sheet">
      <!-- 머리말: 로고, 글 메뉴, 가는 테두리 버튼 -->
      <header class="top">
        <BrandLogo :size="30" />
        <nav class="links" aria-label="소개">
          <a href="#pains">이럴 때 써요</a>
          <a href="#steps">쓰는 방법</a>
          <a href="#faq">자주 묻는 질문</a>
        </nav>
        <div class="top-right">
          <RouterLink to="/signup" class="btn btn-line">회원가입</RouterLink>
        </div>
      </header>

      <!-- 첫 영역: 복숭아 바탕 큰 상자. 왼쪽 인사, 오른쪽 로그인 카드 -->
      <section class="hero" aria-labelledby="landing-title">
        <div class="hero-text">
          <h1 id="landing-title" class="hero-title">
            안녕하세요!<br />
            <span class="grad-word">연구 논문 쓰기를 돕는</span><br />
            Referoom이에요
          </h1>
          <p class="hero-sub">팀이 모은 논문에서 근거를 찾아 답하고, 선행연구 정리와 연구 주제 제안, 원고 수치 검증까지 출처와 함께 도와 드려요.</p>
          <div class="hero-actions">
            <RouterLink to="/signup" class="btn btn-primary">무료로 시작하기</RouterLink>
            <a href="#steps" class="btn btn-quiet more">더 알아보기</a>
          </div>
        </div>

        <div class="hero-card-wrap">
          <form class="card" novalidate aria-labelledby="login-title" @submit.prevent="submit">
            <h2 id="login-title">로그인</h2>
            <div class="field">
              <label class="label" for="username">아이디</label>
              <input id="username" v-model="form.username" class="input" autocomplete="username" />
            </div>
            <div class="field">
              <label class="label" for="password">비밀번호</label>
              <input id="password" v-model="form.password" class="input" type="password" autocomplete="current-password" />
            </div>
            <p v-if="error" class="field-error" role="alert">{{ error }}</p>
            <button class="btn btn-primary submit" type="submit" :disabled="busy">{{ busy ? '로그인하는 중' : '로그인' }}</button>
            <p class="switch">처음 오셨나요? <RouterLink to="/signup">회원가입</RouterLink></p>
          </form>
        </div>
      </section>

      <!-- 무엇이 막히나요: 가는 테두리 카드 + 선 아이콘, 마지막 칸만 복숭아 -->
      <section id="pains" class="pains" aria-labelledby="pains-title">
        <h2 id="pains-title" class="sec-title">논문 읽다가<br />어디서 막히나요?</h2>
        <article v-for="p in PAINS" :key="p.icon" class="pain">
          <div class="pain-head">
            <h3>{{ p.title }}</h3>
            <svg class="pain-icon" width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <template v-if="p.icon === 'term'">
                <path d="M8 9h16a4 4 0 0 1 4 4v18H12a4 4 0 0 1-4-4z" />
                <circle cx="26" cy="27" r="7" fill="var(--c-peach)" />
                <path d="M24 25a2 2 0 1 1 2.5 2c-.5.2-.5.7-.5 1.2M26 30.5v.2" />
              </template>
              <template v-else-if="p.icon === 'formula'">
                <circle cx="20" cy="20" r="13" fill="var(--c-peach)" />
                <path d="M25 13H15l6 7-6 7h10" />
              </template>
              <template v-else-if="p.icon === 'source'">
                <path d="M10 6h14l6 6v22H10z" />
                <path d="M24 6v6h6M14 18h10M14 23h8" />
                <circle cx="25" cy="27" r="5" fill="var(--c-peach)" />
                <path d="M29 31l4 4" />
              </template>
              <template v-else>
                <rect x="6" y="9" width="28" height="22" rx="4" fill="var(--c-peach)" />
                <path d="M16 17l-4 3 4 3M24 17l4 3-4 3M21 15l-2 10" />
              </template>
            </svg>
          </div>
          <p>{{ p.text }}</p>
        </article>
        <RouterLink to="/signup" class="pain pain-cta">
          <span>무료로<br />시작하기</span>
          <span class="arrow" aria-hidden="true"><Icon name="send" :size="18" /></span>
        </RouterLink>
      </section>

      <!-- 어떻게 쓰나요: 세이지 바탕, 번호 단계 + 그림 -->
      <section id="steps" class="steps" aria-labelledby="steps-title">
        <h2 id="steps-title" class="sec-title center">어떻게 쓰나요?</h2>
        <div class="steps-body">
          <ol class="step-list">
            <li v-for="(s, i) in STEPS" :key="s.title" :class="{ on: step === i }">
              <button type="button" :aria-expanded="step === i" @click="step = i">
                <span class="step-no">{{ i + 1 }}</span>
                <span class="step-title">{{ s.title }}</span>
              </button>
              <p v-show="step === i" class="step-text">{{ s.text }}</p>
            </li>
          </ol>
          <div class="steps-art"><ReadersIllust :size="300" /></div>
        </div>
      </section>

      <!-- 자주 묻는 질문: 복숭아 바탕, 펼침 목록 -->
      <section id="faq" class="faq" aria-labelledby="faq-title">
        <h2 id="faq-title" class="sec-title center">자주 묻는 질문</h2>
        <div class="faq-list">
          <details v-for="(f, i) in FAQ" :key="f.q" :open="i === 0">
            <summary>{{ f.q }}</summary>
            <p>{{ f.a }}</p>
          </details>
        </div>
      </section>

      <!-- 시안의 "Book a Free Consultation" 자리: 세이지 상자 -->
      <section class="book" aria-labelledby="book-title">
        <h2 id="book-title">팀을 만들고<br />바로 시작하세요</h2>
        <div class="book-side">
          <p>가입할 때 팀을 새로 만들거나 초대 코드로 참여할 수 있어요. 라이브러리가 비어 있어도 주제만 적으면 arXiv에서 논문을 찾아 드려요.</p>
          <RouterLink to="/signup" class="btn btn-dark">회원가입</RouterLink>
        </div>
      </section>

      <footer class="foot">
        <BrandLogo :size="24" />
        <span>팀 논문 관리와 연구 논문 작성을 근거 기반으로 돕는 서비스</span>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* 시안처럼 바깥은 따뜻한 회색, 안쪽은 흰 종이 한 장 */
.landing {
  min-height: 100vh;
  padding: 20px;
  background: var(--c-surface);
}

.sheet {
  max-width: 1180px;
  margin: 0 auto;
  border-radius: 24px;
  background: var(--c-paper);
  overflow: hidden;
}

.top {
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 22px 40px;
}

.links {
  margin-left: auto;
  display: flex;
  gap: 28px;
  font-size: var(--fs-sm);
}

.links a {
  color: var(--c-ink);
  text-decoration: none;
}

.links a:hover {
  color: var(--c-accent-2);
}

.top-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.top-right .btn {
  text-decoration: none;
}

.hero {
  margin: 0 12px;
  padding: 64px 56px;
  border-radius: 20px;
  background: var(--c-peach);
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 48px;
  align-items: center;
}

.hero-title {
  font-family: var(--font-display);
  font-size: clamp(1.75rem, 3.2vw, 2.5rem);
  font-weight: 400;
  line-height: 1.15;
}

.hero-sub {
  margin-top: 20px;
  max-width: 40ch;
  color: var(--c-text);
}

.hero-actions {
  margin-top: 28px;
  display: flex;
  gap: 8px;
}

.hero-actions .btn {
  min-height: 44px;
  padding: 0 22px;
  text-decoration: none;
}

.more {
  color: var(--c-ink);
}

.hero-card-wrap {
  position: relative;
}

.card {
  padding: 26px;
  border-radius: var(--radius-l);
  background: var(--c-paper);
  box-shadow: var(--shadow-float);
  display: grid;
  gap: 14px;
}

.card h2 {
  font-size: var(--fs-xl);
}

.submit {
  min-height: 44px;
  font-size: var(--fs-md);
}

.switch {
  font-size: var(--fs-sm);
  color: var(--c-ink-muted);
}

.sec-title {
  font-family: var(--font-display);
  font-size: clamp(1.8rem, 3vw, 2.4rem);
  font-weight: 400;
  line-height: 1.2;
}

.center {
  text-align: center;
}

/* 막히는 지점 카드 격자: 제목 칸 + 카드 넷 + 복숭아 칸 */
.pains {
  padding: 88px 56px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.pain {
  min-height: 200px;
  padding: 22px;
  border: 1px solid var(--c-rule-strong);
  border-radius: var(--radius-m);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
}

.pain-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.pain h3 {
  font-family: var(--font-display);
  font-size: 1.3rem;
  font-weight: 400;
  line-height: 1.25;
}

.pain-icon {
  flex: none;
  color: var(--c-ink);
}

.pain p {
  font-size: var(--fs-sm);
  color: var(--c-text);
}

.pain-cta {
  border-color: transparent;
  background: var(--c-peach);
  color: var(--c-ink);
  font-weight: 600;
  text-decoration: none;
  justify-content: flex-end;
  flex-direction: row;
  align-items: flex-end;
}

.pain-cta .arrow {
  margin-left: auto;
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-paper);
  transform: rotate(45deg);
}

.pain-cta:hover .arrow {
  background: var(--c-accent);
  color: var(--c-on-accent);
}

.steps {
  margin: 0 12px;
  padding: 72px 56px;
  border-radius: 20px;
  background: var(--c-sage-bg);
}

.steps-body {
  margin-top: 40px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 40px;
  align-items: center;
}

.step-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}

.step-list li {
  border-radius: var(--radius-m);
}

.step-list li.on {
  background: var(--c-paper);
  box-shadow: var(--shadow-card);
}

.step-list button {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px 8px;
  border: 0;
  background: none;
  text-align: left;
  cursor: pointer;
}

.step-no {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--c-paper);
  color: var(--c-accent);
  font-size: var(--fs-xs);
  font-weight: 700;
}

.on .step-no {
  background: var(--c-accent);
  color: var(--c-on-accent);
}

.step-title {
  font-family: var(--font-display);
  font-size: 1.25rem;
}

.step-text {
  padding: 0 18px 16px 58px;
  font-size: var(--fs-sm);
  color: var(--c-text);
}

.steps-art {
  display: grid;
  place-items: center;
  padding: 24px;
  border-radius: var(--radius-l);
  background: var(--c-paper);
}

.faq {
  padding: 88px 56px;
}

.faq-list {
  max-width: 760px;
  margin: 36px auto 0;
  display: grid;
}

.faq details {
  border-bottom: 1px solid var(--c-rule);
}

.faq details[open] {
  margin: 4px 0;
  border-bottom-color: transparent;
  border-radius: var(--radius-m);
  background: var(--c-peach);
}

.faq summary {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  font-weight: 600;
  list-style: none;
  cursor: pointer;
}

.faq summary::-webkit-details-marker {
  display: none;
}

/* + / − 표시 */
.faq summary::after {
  content: "+";
  font-size: 1.25rem;
  line-height: 1;
  color: var(--c-ink-muted);
}

.faq details[open] summary::after {
  content: "−";
}

.faq details p {
  padding: 0 20px 18px;
  font-size: var(--fs-sm);
  color: var(--c-text);
}

.book {
  margin: 0 12px;
  padding: 48px 56px;
  border-radius: 20px;
  background: var(--c-sage-bg);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 40px;
  align-items: center;
}

.book h2 {
  font-size: clamp(1.6rem, 2.6vw, 2rem);
  font-weight: 400;
}

.book-side p {
  color: var(--c-text);
}

.book-side .btn {
  margin-top: 18px;
  min-height: 44px;
  padding: 0 22px;
  text-decoration: none;
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 40px;
  font-size: var(--fs-xs);
  color: var(--c-ink-muted);
}

@media (max-width: 960px) {
  .hero,
  .steps-body,
  .book {
    grid-template-columns: minmax(0, 1fr);
  }

  .pains {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .links {
    display: none;
  }

  .top-right {
    margin-left: auto;
  }

}

@media (max-width: 600px) {
  .landing {
    padding: 0;
  }

  .sheet {
    border-radius: 0;
  }

  .top {
    padding: 16px 18px;
    gap: 12px;
  }

  .top-right .btn {
    display: none;
  }

  .hero {
    margin: 0;
    padding: 40px 20px;
    border-radius: 0;
  }

  .pains,
  .faq {
    padding: 56px 20px;
    grid-template-columns: minmax(0, 1fr);
  }

  .steps,
  .book {
    margin: 0;
    padding: 48px 20px;
    border-radius: 0;
  }


  .foot {
    flex-direction: column;
    padding: 24px 20px;
  }
}
</style>
