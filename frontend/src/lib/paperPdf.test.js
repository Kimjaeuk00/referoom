import { test } from 'node:test'
import assert from 'node:assert/strict'
import { NotPdfError, PopupBlockedError, clearPdfCache, openPaperPdf, pdfErrorText, pdfFragment } from './paperPdf.js'

test('pdfFragment: 1 이상의 정수 쪽만 #page=N, 나머지는 빈 문자열', () => {
  assert.equal(pdfFragment(4), '#page=4')
  assert.equal(pdfFragment(1), '#page=1')
  for (const bad of [0, null, undefined, -1, 2.5, '3', NaN, Infinity]) assert.equal(pdfFragment(bad), '', String(bad))
})

// 호출 순서를 기록하는 가짜 환경
function setup({ blob = { type: 'application/pdf' }, fetchError = null, openResult } = {}) {
  clearPdfCache({ revokeUrl: () => {} }) // 모듈 캐시가 테스트끼리 새지 않게
  const calls = []
  const tab = { location: { href: '' }, close: () => calls.push('close') }
  const deps = {
    open: (url, target) => { calls.push(`open:${url}:${target}`); return openResult === undefined ? tab : openResult },
    fetchBlob: async (id) => { calls.push(`fetch:${id}`); if (fetchError) throw fetchError; return blob },
    createUrl: () => { calls.push('createUrl'); return 'blob:http://app/abc' },
    revokeUrl: (url) => calls.push(`revoke:${url}`),
    schedule: (fn, ms) => { calls.push(`schedule:${ms}`); deps.runScheduled = fn },
  }
  return { calls, tab, deps }
}

test('정상: 새 탭을 먼저 열고(await 전), 받은 PDF를 blob URL + #page=N으로 연다', async () => {
  const { calls, tab, deps } = setup()
  await openPaperPdf(434253507605, 4, deps)
  assert.deepEqual(calls.slice(0, 2), ['open::_blank', 'fetch:434253507605'])  // open이 fetch보다 먼저
  assert.equal(tab.location.href, 'blob:http://app/abc#page=4')
  assert.ok(!calls.includes('close'))
})

test('정상: 10분 뒤 blob URL을 푸는 예약이 걸린다', async () => {
  const { calls, deps } = setup()
  await openPaperPdf(7, 2, deps)
  assert.ok(calls.includes(`schedule:${10 * 60 * 1000}`))
  assert.ok(!calls.includes('revoke:blob:http://app/abc'))
  deps.runScheduled()
  assert.ok(calls.includes('revoke:blob:http://app/abc'))
})

test('쪽이 없으면 #page 없이 연다', async () => {
  const { tab, deps } = setup()
  await openPaperPdf(7, null, deps)
  assert.equal(tab.location.href, 'blob:http://app/abc')
})

test('새 탭이 막히면 PopupBlockedError이고 서버를 부르지 않는다', async () => {
  const { calls, deps } = setup({ openResult: null })
  await assert.rejects(openPaperPdf(7, 1, deps), PopupBlockedError)
  assert.ok(!calls.some((c) => c.startsWith('fetch')))
})

test('서버 오류(404 등)면 빈 탭을 닫고 오류를 그대로 다시 던진다', async () => {
  const notFound = Object.assign(new Error('x'), { code: 'NOT_FOUND', status: 404 })
  const { calls, tab, deps } = setup({ fetchError: notFound })
  await assert.rejects(openPaperPdf(7, 1, deps), (e) => e === notFound)
  assert.ok(calls.includes('close'))
  assert.equal(tab.location.href, '')
  assert.ok(!calls.includes('createUrl'))
})

test('같은 논문을 다시 열면 PDF를 다시 받지 않고 같은 blob URL을 쓴다(쪽만 다름)', async () => {
  const { calls, tab, deps } = setup()
  await openPaperPdf(7, 5, deps)
  assert.equal(tab.location.href, 'blob:http://app/abc#page=5')
  await openPaperPdf(7, 1, deps)
  assert.equal(tab.location.href, 'blob:http://app/abc#page=1')
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 1)
  assert.equal(calls.filter((c) => c === 'createUrl').length, 1)
})

test('동시에 두 번 눌러도 내려받기는 한 번', async () => {
  const { calls, deps } = setup()
  await Promise.all([openPaperPdf(7, 5, deps), openPaperPdf(7, 1, deps)])
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 1)
})

test('다른 논문은 따로 받는다', async () => {
  const { calls, deps } = setup()
  await openPaperPdf(7, 1, deps)
  await openPaperPdf(8, 1, deps)
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 2)
})

test('blob URL이 풀린 뒤에는 캐시도 비워져 다시 받는다', async () => {
  const { calls, deps } = setup()
  await openPaperPdf(7, 1, deps)
  deps.runScheduled()
  await openPaperPdf(7, 1, deps)
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 2)
})

test('clearPdfCache: 받아 둔 주소를 모두 풀고, 다음에는 다시 받는다', async () => {
  const { calls, deps } = setup()
  await openPaperPdf(7, 1, deps)
  const revoked = []
  clearPdfCache({ revokeUrl: (url) => revoked.push(url) })
  await Promise.resolve() // pending.then이 도는 한 틱
  assert.deepEqual(revoked, ['blob:http://app/abc'])
  await openPaperPdf(7, 1, deps)
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 2)
})

test('비운 뒤 새로 받은 항목은 이전 예약이 지우지 않는다', async () => {
  const { calls, deps } = setup()
  await openPaperPdf(7, 1, deps)
  const oldTimer = deps.runScheduled
  clearPdfCache({ revokeUrl: () => {} })
  await openPaperPdf(7, 1, deps) // 새로 받음
  oldTimer() // 이전 예약이 늦게 돈다
  await openPaperPdf(7, 2, deps) // 새 항목이 남아 있어야 다시 받지 않는다
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 2)
})

test('실패한 내려받기는 캐시하지 않아 다음에 다시 시도한다', async () => {
  const { calls, deps } = setup({ fetchError: new Error('x') })
  await assert.rejects(openPaperPdf(7, 1, deps))
  await assert.rejects(openPaperPdf(7, 1, deps))
  assert.equal(calls.filter((c) => c.startsWith('fetch')).length, 2)
})

test('PDF가 아닌 응답이면 탭을 닫고 NotPdfError', async () => {
  const { calls, deps } = setup({ blob: { type: 'text/html' } })
  await assert.rejects(openPaperPdf(7, 1, deps), NotPdfError)
  assert.ok(calls.includes('close'))
  assert.ok(!calls.includes('createUrl'))
})

test('잘못된 논문 id는 탭을 열기 전에 거절한다', async () => {
  for (const bad of [0, -1, 1.5, '7', null, NaN, 2 ** 60]) {
    const { calls, deps } = setup()
    await assert.rejects(openPaperPdf(bad, 1, deps), TypeError, String(bad))
    assert.deepEqual(calls, [])
  }
})

test('pdfErrorText: 이 기능의 오류는 전용 문구, 나머지는 fallback', () => {
  assert.match(pdfErrorText(new PopupBlockedError()), /팝업/)
  assert.match(pdfErrorText({ code: 'NOT_FOUND' }), /원문 PDF가 없어요/)
  assert.match(pdfErrorText(new NotPdfError()), /PDF로 열 수 없었어요/)
  assert.equal(pdfErrorText({ code: 'TIMEOUT' }, '응답이 지연되고 있어요'), '응답이 지연되고 있어요')
  assert.match(pdfErrorText(new Error('x')), /열지 못했어요/)
})
