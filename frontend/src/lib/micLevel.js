// 마이크 입력 음량 측정: 녹음 중 "소리가 실제로 들어오는지"를 화면에 보여 주기 위한 순수 함수와 브라우저 연결.
// 순수 함수(rmsOf, levelOf, startMeter, stepMeter, micFeedback)는 node --test로 시험하고, watchMic만 브라우저의 AudioContext를 쓴다.

export const SPEECH_RMS = 0.015 // 이 이상이면 사람 목소리가 들어온다고 본다. 조용한 방의 배경 소음은 대개 0.01 안팎이다
export const HOLD_MS = 700 // 말 사이의 짧은 쉼에서 표시가 깜박이지 않도록 유지하는 시간
export const SILENT_WARN_MS = 3000 // 이만큼 목소리가 없으면 마이크를 확인하라고 알린다
const FULL_RMS = 0.2 // 막대가 가득 차는 음량. 보통 목소리는 0.02~0.2

// 막대 7개의 상대 높이(가운데가 가장 높다)와, 입력 음량(0~1)에 맞춘 막대 높이(px)
export const BAR_WEIGHTS = [0.45, 0.7, 0.9, 1, 0.9, 0.7, 0.45]
export const barPx = (level, weight, maxPx = 36) => Math.max(4, Math.round(level * weight * maxPx))

export function rmsOf(samples) {
  if (!samples?.length) return 0
  let sum = 0
  for (let i = 0; i < samples.length; i += 1) sum += samples[i] * samples[i]
  return Math.sqrt(sum / samples.length)
}

// 조용한 목소리도 막대에 보이도록 제곱근으로 펴 준다 (0~1)
export const levelOf = (rms) => Math.min(1, Math.sqrt(Math.max(0, rms) / FULL_RMS))

export const startMeter = (now) => ({ level: 0, speaking: false, lastSpeechAt: null, startedAt: now, silentMs: 0 })

// 막대는 소리가 커질 때 바로 올라가고, 작아질 때는 천천히 내려온다
export function stepMeter(prev, rms, now) {
  const target = levelOf(rms)
  const level = target > prev.level ? target : prev.level * 0.8 + target * 0.2
  const lastSpeechAt = rms >= SPEECH_RMS ? now : prev.lastSpeechAt
  return {
    level,
    lastSpeechAt,
    startedAt: prev.startedAt,
    speaking: lastSpeechAt !== null && now - lastSpeechAt <= HOLD_MS,
    silentMs: now - (lastSpeechAt ?? prev.startedAt),
  }
}

// 화면에 보여 줄 상태: hearing(인식 중) / waiting(말을 기다리는 중) / quiet(한동안 소리가 없음)
export function micFeedback({ speaking, silentMs }) {
  if (speaking) return 'hearing'
  return silentMs >= SILENT_WARN_MS ? 'quiet' : 'waiting'
}

// 브라우저는 사용자 조작 직후가 아니면 AudioContext를 멈춘 채로 둘 수 있다(특히 마이크 권한 창을 거친 뒤).
// 그래서 녹음 버튼을 누른 직후(권한을 묻기 전)에 먼저 만들어 두고, 권한을 받으면 watchMic에 넘긴다. 못 만들면 null.
export function createMeterContext() {
  const Context = globalThis.AudioContext || globalThis.webkitAudioContext
  if (!Context) return null
  try {
    const context = new Context()
    context.resume?.()?.catch?.(() => {})
    return context
  } catch {
    return null
  }
}

// stream의 음량을 interval(ms)마다 onUpdate({ ...meter, available })로 알린다. 반환값은 멈추는 함수.
// AudioContext를 못 쓰거나 'running'이 아니면 available=false로 알려서, 화면이 "소리가 없다"고 잘못 경고하지 않게 한다.
export function watchMic(stream, onUpdate, { now = () => performance.now(), interval = 80, context: given = null } = {}) {
  const context = given ?? createMeterContext()
  if (!context) return () => {}
  let source
  let timer
  try {
    source = context.createMediaStreamSource(stream)
    const analyser = context.createAnalyser()
    analyser.fftSize = 1024
    source.connect(analyser) // 스피커로 보내지 않는다(되울림 방지)
    context.resume?.()?.catch?.(() => {}) // 이미 만든 컨텍스트라도 다시 한 번 깨운다
    const samples = new Float32Array(analyser.fftSize)
    let meter = startMeter(now())
    timer = setInterval(() => {
      analyser.getFloatTimeDomainData(samples)
      meter = stepMeter(meter, rmsOf(samples), now())
      onUpdate({ ...meter, available: context.state === 'running' })
    }, interval)
  } catch {
    clearInterval(timer)
    try { context.close?.()?.catch?.(() => {}) } catch { /* 이미 닫힘 */ }
    return () => {}
  }
  return () => {
    clearInterval(timer)
    try { source.disconnect() } catch { /* 이미 끊김 */ }
    try { context.close?.()?.catch?.(() => {}) } catch { /* 이미 닫힘 */ }
  }
}
