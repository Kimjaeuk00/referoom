import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasVerifyConsent, rememberVerifyConsent, VERIFY_CONSENT_KEY } from './consent.js'

const memory = () => { const m = new Map(); return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), data: m } }
const blocked = { getItem() { throw new Error('blocked') }, setItem() { throw new Error('blocked') } }

test('동의는 한 번 기억하면 이어진다', () => {
  const s = memory()
  assert.equal(hasVerifyConsent(s), false)
  rememberVerifyConsent(s)
  assert.equal(hasVerifyConsent(s), true)
  assert.deepEqual([...s.data.keys()], [VERIFY_CONSENT_KEY])
})

test('저장소가 막히면 오류 없이 매번 묻는다', () => {
  assert.doesNotThrow(() => rememberVerifyConsent(blocked))
  assert.equal(hasVerifyConsent(blocked), false)
})
