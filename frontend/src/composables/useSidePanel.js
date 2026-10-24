import { ref, watch } from 'vue'

// 질문하기 왼쪽 논문 패널의 열림과 너비. 상단 ☰ 버튼(AppShell)과 질문하기 화면(AskView)이 함께 쓴다.
// 열림·너비는 이 브라우저에만 기억한다(저장이 막혀 있으면 기본값으로 동작).
export const SIDE_MIN = 240
export const SIDE_MAX = 560
export const SIDE_DEFAULT = 320

const NARROW = '(max-width: 900px)'
const read = (key) => {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
const write = (key, value) => {
  try {
    localStorage.setItem(key, value)
  } catch {
    // 사생활 보호 모드 등에서는 기억하지 않는다
  }
}

export const isNarrow = () => window.matchMedia(NARROW).matches
export const clampSide = (w) => Math.min(SIDE_MAX, Math.max(SIDE_MIN, Math.round(w)))

// 좁은 화면에서는 늘 닫힌 채로 시작한다
export const sideOpen = ref(!isNarrow() && read('referoom.sideOpen') !== '0')
export const sideWidth = ref(clampSide(Number(read('referoom.sideWidth')) || SIDE_DEFAULT))

watch(sideOpen, (open) => !isNarrow() && write('referoom.sideOpen', open ? '1' : '0'))
watch(sideWidth, (w) => write('referoom.sideWidth', String(w)))
