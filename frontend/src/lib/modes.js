// 모드(튜터·선행연구·주제·검증)의 요청 형식, 입력 규칙, 표시 이름 (기능명세서 v0.2 2.0~2.10, PRD v0.2 8절).
// 서버 응답 형식에 기대는 부분은 이 파일과 api/mock/index.js에만 둔다. 서버가 형식을 바꾸면 이 둘만 고친다.
// node --test로 시험하려고 api/client.js 같은 브라우저 전용 모듈은 가져오지 않는다 (타임아웃은 이름으로만 돌려준다).

export const MAX_COLLECT = 10 // 한 번에 수집하거나 대상으로 고를 수 있는 논문 수 (서버 상한과 같다)
export const EMPTY_CELL = '논문에 명시되지 않음'

/** 수집 배치가 끝난 뒤 라이브러리에 들어 있는 논문의 id (새로 색인했거나 이미 있어 건너뛴 것). 실패한 논문과 아직 id가 없는 항목은 뺀다. */
export const collectedPaperIds = (batch) =>
  (batch?.papers ?? []).filter((p) => (p.status === 'indexed' || p.status === 'skipped') && p.paper_id != null).map((p) => p.paper_id)

export const MODES = {
  tutor: { label: '튜터', placeholder: '논문에 대해 궁금한 점을 물어보세요', max: 1000, path: '/rag-query', timeoutKey: 'query' },
  prior: { label: '선행연구', placeholder: '조사할 연구 주제를 입력하세요', max: 1000, path: '/rag-query', timeoutKey: 'query', hint: '주제를 찾아 논문을 모으고, 모은 논문을 비교해 정리해요.' },
  topic: { label: '주제', placeholder: '원하는 방향을 적어 주세요 (비워도 돼요)', max: 1000, path: '/topic-suggest', timeoutKey: 'long', hint: '고른 논문의 한계를 바탕으로 연구 주제를 제안해요.' },
  verify: { label: '검증', placeholder: '원고 문단이나 수치를 붙여 넣으세요', max: 3000, path: '/verify', timeoutKey: 'long', hint: '원고의 수치를 선행연구 근거와 대조해요.' },
}

export const MODE_ORDER = ['tutor', 'prior', 'topic', 'verify']
export const CHIP_MODES = ['prior', 'topic', 'verify'] // 입력창 아래 칩으로 보여 주는 모드. 모두 끄면 튜터다.

/** 화면과 기록에 보여 줄 원고 요약: 앞 80자와 전체 글자 수. 원고 전체는 요청을 보낼 때만 쓴다. */
export function manuscriptPreview(text) {
  const flat = String(text ?? '').replace(/\s+/g, ' ').trim()
  return `${flat.length > 80 ? `${flat.slice(0, 80)}…` : flat} (원고 ${flat.length.toLocaleString('ko-KR')}자)`
}

/** 본인 결과의 차이 값을 '+0.9p'처럼 */
export function formatDelta(delta) {
  const value = Number(delta?.value)
  if (!Number.isFinite(value)) return ''
  return `${value > 0 ? '+' : ''}${value}p${delta.vs ? ` (vs ${delta.vs})` : ''}`
}

export const isMode = (value) => MODE_ORDER.includes(value)

const ids = (list) => (list ?? []).map(Number)

/**
 * 모드에 맞는 요청을 만든다. 반환: { path, body, timeoutKey }.
 * - level은 '더 쉽게/더 깊게'처럼 그 요청 1회에만 보낼 때(level 인자)만 body에 들어간다. 설정이나 프로필 값은 보내지 않는다.
 * - scope는 튜터가 쓰는 범위(scopeBody 결과, 팀 전체면 undefined). 선행연구는 priorIds(수집·선택한 논문)가 있으면 그것으로 바꾼다.
 * - 주제·검증의 대상 논문은 paperIds. 검증은 비어 있으면 null(팀 전체)로 보낸다.
 */
export function buildRequest(mode, { question = '', view, source = 'all', scope, paperIds = [], priorIds = [], level } = {}) {
  const spec = MODES[mode]
  if (!spec) throw new Error(`알 수 없는 모드: ${mode}`)
  const text = question.trim()
  const withLevel = level ? { level } : {}
  if (mode === 'tutor') return { path: spec.path, timeoutKey: spec.timeoutKey, body: { question: text, mode, source, scope, view, top_k: 5, ...withLevel } }
  if (mode === 'prior') {
    const priorScope = priorIds.length ? { type: 'paper', ids: ids(priorIds) } : scope
    return { path: spec.path, timeoutKey: spec.timeoutKey, body: { question: text, mode, source, scope: priorScope, view, top_k: 5, ...withLevel } }
  }
  if (mode === 'topic') return { path: spec.path, timeoutKey: spec.timeoutKey, body: { paper_ids: ids(paperIds), hint: text, n: 4, view } }
  return { path: spec.path, timeoutKey: spec.timeoutKey, body: { text, paper_ids: paperIds.length ? ids(paperIds) : null, view } }
}

/** 보내기 전에 입력을 확인한다. 반환: null(보내도 됨) 또는 사용자에게 보여 줄 이유. */
export function validateInput(mode, text, paperIds = []) {
  const spec = MODES[mode]
  if (!spec) return '알 수 없는 모드예요.'
  const length = (text ?? '').trim().length
  if (mode === 'topic') {
    if (paperIds.length === 0) return '대상 논문을 선택하세요.'
    if (paperIds.length > MAX_COLLECT) return `대상 논문은 ${MAX_COLLECT}편까지 고를 수 있어요.`
  } else if (mode === 'verify') {
    if (length < 10) return '원고를 10자 이상 입력하세요.'
  } else if (length < 2) {
    return '2자 이상 입력하세요.'
  }
  if (length > spec.max) return `${spec.max.toLocaleString('ko-KR')}자까지 입력할 수 있어요.`
  return null
}

// 검증 판정. 색만으로 구분하지 않도록 아이콘 글자와 이름을 함께 쓴다 (tone은 색 계열 이름).
export const VERDICTS = {
  match: { label: '일치', icon: '✓', tone: 'good', desc: '원고가 인용한 선행 값이 논문 값과 같아요.' },
  mismatch: { label: '불일치', icon: '✕', tone: 'bad', desc: '논문 값과 달라요. 논문 값과 쪽수를 확인하세요.' },
  condition_differs: { label: '조건 다름', icon: '≠', tone: 'warn', desc: '값은 있지만 데이터셋·지표·모델 크기 같은 조건이 달라 바로 비교하기 어려워요.' },
  not_found: { label: '근거 없음', icon: '?', tone: 'muted', desc: '라이브러리에서 이 값을 찾지 못했어요.' },
  own_result: { label: '본인 결과', icon: '◎', tone: 'info', desc: '내 실험 값이라 검증 대상이 아니에요. 기준 값과의 차이만 계산해요.' },
}

export const verdictOf = (key) => VERDICTS[key] ?? { label: key ?? '알 수 없음', icon: '·', tone: 'muted', desc: '' }

// 주제 후보의 관점 (기능명세서 2.9)
export const PERSPECTIVES = {
  limitation_fix: '한계 직접 해결',
  combine: '방법 결합',
  extend: '도메인·데이터 확장',
  efficiency: '효율·자원',
  evaluation: '평가·분석',
}

export const perspectiveOf = (key) => PERSPECTIVES[key] ?? key ?? ''

// 선행연구 정리표 (기능명세서 2.8 F8-4): 논문별 행, 열은 아래 순서. 값이 없으면 EMPTY_CELL.
export const PRIOR_COLUMNS = [
  ['problem', '문제'],
  ['method', '방법'],
  ['dataset', '데이터셋'],
  ['metric', '지표'],
  ['result', '주요 결과'],
  ['limitation', '한계'],
]

const cellText = (row, key) => String(row[key] ?? '').replace(/\s+/g, ' ').trim()
const cellOrEmpty = (row, key) => cellText(row, key) || EMPTY_CELL
const cited = (row, key) => (row.labels?.[key] && cellText(row, key) ? ` [${row.labels[key]}]` : '')

/** 정리표를 Markdown 표로. 칸의 | 는 이스케이프하고 줄바꿈은 공백으로 바꾼다. */
export function priorTableToMarkdown(rows) {
  const esc = (text) => text.replace(/\|/g, '\\|')
  const head = ['논문', ...PRIOR_COLUMNS.map(([, name]) => name)]
  const lines = [`| ${head.join(' | ')} |`, `| ${head.map(() => '---').join(' | ')} |`]
  for (const row of rows ?? []) {
    const cells = [esc(cellOrEmpty(row, 'title')), ...PRIOR_COLUMNS.map(([key]) => esc(cellOrEmpty(row, key) + cited(row, key)))]
    lines.push(`| ${cells.join(' | ')} |`)
  }
  return lines.join('\n')
}

// 엑셀에서 열 때 =, +, -, @로 시작하는 칸이 수식으로 실행되지 않도록 앞에 작은따옴표를 붙인다 (CSV 수식 주입 방지)
export function csvCell(value) {
  let text = String(value ?? '')
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** 정리표를 CSV로. 엑셀에서 한글이 깨지지 않게 하려면 파일을 저장할 때 { bom: true }로 UTF-8 BOM을 붙인다. */
export function priorTableToCsv(rows, { bom = false } = {}) {
  const head = ['논문', ...PRIOR_COLUMNS.map(([, name]) => name)]
  const lines = [head.map(csvCell).join(',')]
  for (const row of rows ?? []) {
    lines.push([cellOrEmpty(row, 'title'), ...PRIOR_COLUMNS.map(([key]) => cellOrEmpty(row, key) + cited(row, key))].map(csvCell).join(','))
  }
  return (bom ? '﻿' : '') + lines.join('\r\n')
}
