// 실행: npm test (node --test)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { decodeJwt, isExpired } from './jwt.js'
import { ApiError, errorText, normalizeError } from '../api/errors.js'

function token(payload) {
  const enc = (o) => Buffer.from(JSON.stringify(o)).toString('base64url')
  return `${enc({ alg: 'HS256' })}.${enc(payload)}.sig`
}

test('decodeJwt: 한글이 든 payload와 claim을 읽는다', () => {
  const claims = decodeJwt(token({ sub: '12', username: '민수', team_id: 3, exp: 2_000_000_000 }))
  assert.equal(claims.username, '민수')
  assert.equal(claims.team_id, 3)
  assert.equal(decodeJwt('not-a-token'), null)
  assert.equal(decodeJwt(null), null)
})

test('isExpired: exp가 없거나 지났으면 만료', () => {
  const now = 1_700_000_000_000
  assert.equal(isExpired({ exp: now / 1000 + 60 }, now), false)
  assert.equal(isExpired({ exp: now / 1000 - 1 }, now), true)
  assert.equal(isExpired({}, now), true)
  assert.equal(isExpired(null, now), true)
})

test('normalizeError: AI 서비스·인증서버 두 에러 형식 모두 code를 읽는다', () => {
  assert.equal(normalizeError(403, { detail: 'x', code: 'NO_TEAM' }).code, 'NO_TEAM')
  assert.equal(normalizeError(401, { ok: false, error: 'invalid credentials', code: 'INVALID_CREDENTIALS' }).code, 'INVALID_CREDENTIALS')
  // code가 없으면 상태 코드로 정한다
  assert.equal(normalizeError(409, null).code, 'CONFLICT')
  assert.equal(normalizeError(503, {}).retryable, true)
  assert.equal(normalizeError(500, {}).code, 'UNKNOWN')
})

test('normalizeError: 서버 detail은 사용자 문구로 쓰지 않는다', () => {
  const err = normalizeError(503, { detail: 'Traceback: faiss index missing', code: 'NOT_READY' })
  assert.ok(!err.message.includes('Traceback'))
  assert.equal(err.message, '서비스를 준비 중이에요. 잠시 후 다시 시도해 주세요.')
})

test('normalizeError: FastAPI 422 검증 응답에서 필드 이름을 뽑는다', () => {
  const err = normalizeError(422, { detail: [{ loc: ['body', 'question'], msg: 'too short' }] })
  assert.deepEqual(err.fields, ['question'])
})

test('errorText: 화면별 문구로 덮어쓸 수 있다', () => {
  const err = new ApiError({ status: 409, code: 'CONFLICT' })
  assert.equal(errorText(err, { CONFLICT: '이미 쓰고 있는 아이디예요' }), '이미 쓰고 있는 아이디예요')
  assert.equal(errorText(new Error('boom')), '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.')
})

test('format: 저자 문자열·배열, 배치 종료, 낭독용 평문', async () => {
  const { authorsShort, isBatchDone, speakable } = await import('./format.js')
  assert.equal(authorsShort('Edward J. Hu, Yelong Shen, Phillip Wallis'), 'Hu 외 2명')
  assert.equal(authorsShort(['Dawid J. Kopiczko']), 'Kopiczko')
  assert.equal(authorsShort(''), '')
  assert.equal(isBatchDone({ status: 'running' }), false)
  assert.equal(isBatchDone({ status: 'done' }), true)
  assert.equal(isBatchDone({ status: 'failed' }), true)
  assert.equal(isBatchDone(null), false)
  assert.equal(speakable('**LoRA**는 $W_0$를 고정해요 [S1].\n\n$$x$$'), 'LoRA는 W 0를 고정해요. 수식은 화면에서 확인하세요.')
  assert.equal(speakable('가'.repeat(700)).length, 601)
})

test('safeUrl: http(s)만 링크로 쓴다', async () => {
  const { safeUrl } = await import('./format.js')
  assert.equal(safeUrl('https://arxiv.org/abs/2106.09685'), 'https://arxiv.org/abs/2106.09685')
  assert.equal(safeUrl('javascript:alert(1)'), null)
  assert.equal(safeUrl(' JavaScript:alert(1)'), null)
  assert.equal(safeUrl('data:text/html,x'), null)
  assert.equal(safeUrl(null), null)
})
