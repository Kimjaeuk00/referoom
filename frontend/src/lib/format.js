export const PAPER_STATUS = { pending: '색인 중', indexed: '색인 완료', failed: '실패' }
export const BATCH_ITEM_STATUS = { pending: '대기', indexed: '완료', failed: '실패', skipped: '건너뜀' }

// 배치 상태가 running이 아니면 끝난 것(done | failed)
export const isBatchDone = (batch) => Boolean(batch) && batch.status !== 'running'
export const SOURCE_TYPE = { zotero: 'Zotero', pdf: 'PDF', web: '웹 수집' }

const dateFmt = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' })
const dateTimeFmt = new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })

export function formatDate(iso) {
  return iso ? dateFmt.format(new Date(iso)) : '–'
}

export function formatDateTime(iso) {
  return iso ? dateTimeFmt.format(new Date(iso)) : '–'
}

// 저자는 "A, B, C" 문자열(GET /papers) 또는 배열(후보 목록)로 온다
export function authorsShort(authors) {
  if (typeof authors === 'string') authors = authors.split(',').map((a) => a.trim()).filter(Boolean)
  if (!authors?.length) return ''
  const first = authors[0].split(' ').pop()
  return authors.length > 1 ? `${first} 외 ${authors.length - 1}명` : first
}

// 답변 마크다운을 낭독용 평문으로. 출처 표시·수식·기호를 빼고 600자에서 자른다(DEV_04 열린 질문 4).
export function speakable(markdown, max = 600) {
  const text = String(markdown ?? '')
    .replace(/\$\$[\s\S]*?\$\$/g, ' 수식은 화면에서 확인하세요. ')
    .replace(/\$([^$\n]+)\$/g, (_, tex) => tex.replace(/\\[a-zA-Z]+|[{}^_\\]/g, ' '))
    .replace(/\s*\[S\d+\]/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[*_`#>|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return text.length > max ? `${text.slice(0, max)}…` : text
}

// 서버가 준 링크(Zotero·웹 수집 주소)는 http(s)만 링크로 쓴다. javascript: 같은 주소는 버린다.
export function safeUrl(url) {
  try {
    return ['http:', 'https:'].includes(new URL(url).protocol) ? url : null
  } catch {
    return null
  }
}

// 출처 알약 색: S1, S2, ... 순서대로 네 가지 색을 돌려 쓴다
export const toneOfLabel = (label) => String((Number(String(label).slice(1)) - 1 + 4) % 4)

// 태그 색: 같은 태그는 어느 화면에서나 같은 색
export function toneOfTag(tag) {
  let h = 0
  for (const ch of String(tag)) h = (h * 31 + ch.codePointAt(0)) >>> 0
  return `tone-${h % 4}`
}
