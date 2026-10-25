import { computed } from 'vue'
import { apiBlob, BASE_URL } from '@/api/client'

export { speakable } from './format'

// 녹음·재생 composable은 음성 담당 파일이다(composables/useRecorder.js, useAudioPlayer.js). 프론트는 가져다 쓰기만 하고,
// 파일이 아직 없으면 음성 메뉴와 버튼을 숨긴다. 실제 파일의 모양이 달라지면 이 파일만 고치면 된다.
//   useRecorder()    → { state: Ref<'idle'|'recording'|'processing'|'error'>, start(): Promise, stop(): Promise<Blob> }  (그대로 쓴다)
//   원본 useAudioPlayer({ apiBlob, baseUrl }) → { state: Ref<'idle'|'loading'|'playing'|'error'>, play(경로|전체 주소), stop(), dispose() }
//   화면에 내놓는 useAudioPlayer()            → 위에 playing(= state가 'playing') 을 더한 것. apiBlob(Bearer·401 처리)과 baseUrl은 여기서 넣어 준다.
const modules = import.meta.glob(['../composables/useRecorder.js', '../composables/useAudioPlayer.js'], { eager: true })

export const useRecorder = modules['../composables/useRecorder.js']?.useRecorder ?? null
const createPlayer = modules['../composables/useAudioPlayer.js']?.useAudioPlayer ?? null
export const useAudioPlayer = createPlayer
  ? () => {
      const player = createPlayer({ apiBlob, baseUrl: BASE_URL.voice })
      return { ...player, playing: computed(() => player.state.value === 'playing') }
    }
  : null
export const voiceAvailable = Boolean(useRecorder && useAudioPlayer)

export const MAX_RECORD_SECONDS = 60
export const audioUrl = (path) => new URL(path, BASE_URL.voice).href

// useRecorder의 Blob은 webm 또는 mp4(DEV_04 7절). 서버가 확장자로 형식을 알아보게 이름을 붙인다.
export const audioFileName = (blob) => (blob.type.includes('mp4') ? 'question.mp4' : 'question.webm')

export function micErrorText(error) {
  if (!window.isSecureContext) return '마이크는 localhost나 https 주소에서만 켜져요.'
  if (error?.name === 'NotAllowedError') return '마이크 권한이 꺼져 있어요. 주소창 왼쪽의 사이트 설정에서 마이크를 허용해 주세요.'
  if (error?.name === 'NotFoundError') return '연결된 마이크를 찾지 못했어요.'
  return '녹음을 시작하지 못했어요. 다시 눌러 보세요.'
}
