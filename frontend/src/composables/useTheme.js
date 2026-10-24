import { ref, watch } from 'vue'

// 화면 모드: 'system'(기기 설정 따름) | 'light' | 'dark'. 고른 값은 이 브라우저에만 기억한다.
const KEY = 'referoom.theme'
const media = window.matchMedia('(prefers-color-scheme: dark)')

function read() {
  try {
    return localStorage.getItem(KEY) || 'system'
  } catch {
    return 'system'
  }
}

export const themePref = ref(read())

function apply() {
  const dark = themePref.value === 'dark' || (themePref.value === 'system' && media.matches)
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
}

watch(themePref, (pref) => {
  try {
    localStorage.setItem(KEY, pref)
  } catch {
    // 저장이 막혀 있으면 이번 방문 동안만 적용
  }
  apply()
})
media.addEventListener('change', () => themePref.value === 'system' && apply())
apply()

export const THEMES = [
  ['system', '시스템'],
  ['light', '밝게'],
  ['dark', '어둡게'],
]
