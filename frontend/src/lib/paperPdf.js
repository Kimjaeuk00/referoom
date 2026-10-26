// 근거(논문 id + 쪽)를 눌렀을 때 팀 라이브러리의 원본 PDF를 새 탭에서 그 쪽으로 연다.
// <a href>는 Authorization 헤더를 못 붙이므로 Bearer로 받아 Blob URL로 연다. 브라우저 내장 PDF 뷰어가 #page=N을 알아본다.

export class PopupBlockedError extends Error {
  constructor() {
    super('popup blocked')
    this.name = 'PopupBlockedError'
  }
}

export class NotPdfError extends Error {
  constructor() {
    super('response is not a pdf')
    this.name = 'NotPdfError'
  }
}

const REVOKE_AFTER_MS = 10 * 60 * 1000 // 새 탭이 PDF를 다 읽은 뒤 Blob URL을 풀어 메모리를 돌려준다

const urlCache = new Map() // paperId → Promise<blob URL>
// 로그아웃·세션 만료 때 받아 둔 PDF를 모두 버린다. 다른 계정이 같은 논문 id로 이전 팀의 PDF를 보지 못하게 주소까지 푼다
export function clearPdfCache({ revokeUrl = (url) => URL.revokeObjectURL(url) } = {}) {
  for (const pending of urlCache.values()) pending.then(revokeUrl, () => {})
  urlCache.clear()
}

export const pdfFragment = (page) => (Number.isInteger(page) && page >= 1 ? `#page=${page}` : '')

// 테스트에서는 deps로 바꿔 끼운다. 기본 구현은 필요할 때만 불러온다(@ 별칭은 node --test가 모른다)
async function defaultFetchBlob(paperId) {
  const { api, TIMEOUT } = await import('@/api/client')
  return api.rag(`/papers/${paperId}/file`, { as: 'blob', timeout: TIMEOUT.upload })
}

export async function openPaperPdf(paperId, page, deps = {}) {
  if (!Number.isSafeInteger(paperId) || paperId <= 0) throw new TypeError('invalid paper id')
  const {
    open = (...args) => window.open(...args),
    fetchBlob = defaultFetchBlob,
    createUrl = (blob) => URL.createObjectURL(blob),
    revokeUrl = (url) => URL.revokeObjectURL(url),
    schedule = (fn, ms) => setTimeout(fn, ms),
  } = deps

  // 반드시 await보다 먼저: 클릭 직후가 아니면 브라우저가 새 탭을 팝업으로 막는다
  const tab = open('', '_blank')
  if (!tab) throw new PopupBlockedError()
  try {
    // 같은 논문은 받아 둔 PDF의 Blob URL을 다시 쓴다. 풀리는 시점(REVOKE_AFTER_MS)에 캐시도 비운다
    let pending = urlCache.get(paperId)
    if (!pending) {
      pending = (async () => {
        const blob = await fetchBlob(paperId)
        if (blob?.type !== 'application/pdf') throw new NotPdfError()
        const url = createUrl(blob)
        schedule(() => {
          revokeUrl(url)
          if (urlCache.get(paperId) === pending) urlCache.delete(paperId) // 그 사이 비우고 새로 받은 것은 지우지 않는다
        }, REVOKE_AFTER_MS)
        return url
      })()
      urlCache.set(paperId, pending)
      pending.catch(() => {
        if (urlCache.get(paperId) === pending) urlCache.delete(paperId) // 실패는 캐시하지 않는다
      })
    }
    const url = await pending
    tab.location.href = url + pdfFragment(page)
  } catch (error) {
    try { tab.close() } catch { /* 이미 닫힘 */ }
    throw error
  }
}

// 이 기능에서만 다르게 말할 오류. 나머지는 fallback(보통 errorText(error))을 쓴다
export function pdfErrorText(error, fallback = '원문 PDF를 열지 못했어요. 잠시 후 다시 시도해 주세요.') {
  if (error instanceof PopupBlockedError) return '새 탭이 막혔어요. 이 사이트의 팝업을 허용해 주세요.'
  if (error?.code === 'NOT_FOUND') return '서버에 원문 PDF가 없어요. 라이브러리를 동기화해 보세요.'
  if (error instanceof NotPdfError) return '원문을 PDF로 열 수 없었어요.'
  return fallback
}
