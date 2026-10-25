import { test } from 'node:test'
import assert from 'node:assert/strict'
import { HOLD_MS, SILENT_WARN_MS, SPEECH_RMS, levelOf, micFeedback, rmsOf, startMeter, stepMeter, watchMic } from './micLevel.js'

test('rmsOf: 무음은 0, 진폭 0.1의 일정한 신호는 0.1', () => {
  assert.equal(rmsOf(new Float32Array(100)), 0)
  assert.ok(Math.abs(rmsOf(new Float32Array(100).fill(-0.1)) - 0.1) < 1e-6)
  assert.equal(rmsOf([]), 0)
  assert.equal(rmsOf(undefined), 0)
})

test('levelOf: 0~1 안에서 커질수록 늘고, 작은 목소리도 보이게 편다', () => {
  assert.equal(levelOf(0), 0)
  assert.equal(levelOf(1), 1)
  assert.equal(levelOf(-1), 0)
  assert.ok(levelOf(0.02) > 0.3 && levelOf(0.02) < levelOf(0.1))
})

test('stepMeter: 기준 이상의 소리가 들어오면 speaking, 쉼은 HOLD_MS 동안만 유지', () => {
  let m = startMeter(1000)
  m = stepMeter(m, SPEECH_RMS, 1100)
  assert.equal(m.speaking, true)
  m = stepMeter(m, 0, 1100 + HOLD_MS) // 정확히 HOLD_MS까지는 유지
  assert.equal(m.speaking, true)
  m = stepMeter(m, 0, 1100 + HOLD_MS + 1)
  assert.equal(m.speaking, false)
})

test('stepMeter: 기준 바로 아래 소리는 목소리로 치지 않는다', () => {
  const m = stepMeter(startMeter(0), SPEECH_RMS - 0.001, 100)
  assert.equal(m.speaking, false)
  assert.equal(m.lastSpeechAt, null)
})

test('stepMeter: 막대는 바로 올라가고 천천히 내려온다', () => {
  let m = stepMeter(startMeter(0), 0.2, 80)
  assert.equal(m.level, 1)
  m = stepMeter(m, 0, 160)
  assert.ok(m.level > 0.7 && m.level < 1)
})

test('stepMeter: 목소리가 없던 시간은 시작 시각부터, 있었다면 마지막 목소리부터 센다', () => {
  let m = stepMeter(startMeter(1000), 0, 3500)
  assert.equal(m.silentMs, 2500)
  m = stepMeter(m, 0.1, 4000)
  m = stepMeter(m, 0, 5000)
  assert.equal(m.silentMs, 1000)
})

test('micFeedback: 인식 중 / 기다리는 중 / 소리 없음', () => {
  assert.equal(micFeedback({ speaking: true, silentMs: 99999 }), 'hearing')
  assert.equal(micFeedback({ speaking: false, silentMs: SILENT_WARN_MS - 1 }), 'waiting')
  assert.equal(micFeedback({ speaking: false, silentMs: SILENT_WARN_MS }), 'quiet')
})

test('watchMic: AudioContext가 없으면 아무 일도 하지 않는다', () => {
  assert.equal(globalThis.AudioContext, undefined)
  const stop = watchMic({}, () => assert.fail('호출되면 안 된다'))
  assert.doesNotThrow(stop)
})

function fakeAudio(amplitude, state = 'running') {
  const closed = []
  globalThis.AudioContext = class {
    state = state
    createMediaStreamSource() { return { connect() {}, disconnect() {} } }
    createAnalyser() { return { fftSize: 0, getFloatTimeDomainData: (a) => a.fill(amplitude) } }
    resume() { return Promise.resolve() }
    close() { closed.push(true); return Promise.resolve() }
  }
  return closed
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

test('watchMic: 소리가 들어오면 주기적으로 알리고, 멈추면 닫는다', async () => {
  const closed = fakeAudio(0.1)
  const updates = []
  const stop = watchMic({}, (u) => updates.push(u), { interval: 5 })
  await sleep(40)
  stop()
  const count = updates.length
  assert.ok(count >= 2)
  assert.ok(updates.at(-1).speaking && updates.at(-1).available && updates.at(-1).level > 0.5)
  assert.deepEqual(closed, [true])
  await sleep(20)
  assert.equal(updates.length, count) // 멈춘 뒤에는 더 알리지 않는다
  delete globalThis.AudioContext
})

test('watchMic: 컨텍스트가 running이 아니면 available=false (소리 없음 경고를 막는다)', async () => {
  fakeAudio(0, 'suspended')
  const updates = []
  const stop = watchMic({}, (u) => updates.push(u), { interval: 5 })
  await sleep(30)
  stop()
  assert.ok(updates.length >= 1 && updates.every((u) => u.available === false))
  delete globalThis.AudioContext
})

test('watchMic: 미리 만든 컨텍스트를 받아 쓰고, 멈추면 그 컨텍스트를 닫는다', async () => {
  const closed = fakeAudio(0.1)
  const context = new globalThis.AudioContext()
  delete globalThis.AudioContext // 새로 만들지 못하게 해서 넘겨 준 컨텍스트만 쓰는지 본다
  const updates = []
  const stop = watchMic({}, (u) => updates.push(u), { interval: 5, context })
  await sleep(30)
  stop()
  assert.ok(updates.length >= 1 && updates.at(-1).speaking)
  assert.deepEqual(closed, [true])
})

test('createMeterContext: 지원하지 않으면 null', async () => {
  const { createMeterContext } = await import('./micLevel.js')
  assert.equal(globalThis.AudioContext, undefined)
  assert.equal(createMeterContext(), null)
})
