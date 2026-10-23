// VITE_USE_MOCK=true일 때만 불러온다. 서버 대신 같은 모양의 응답을 0.5~3초 지연 후 돌려준다(DEV_02 6절).
// 응답 모양은 DEV_01(인증)·DEV_03(라이브러리)·DEV_04(질의·음성)의 예시 JSON을 따른다.
// 데모 흐름은 DEV_05 5.1과 같다: LoRA·QLoRA는 이미 라이브러리에 있고, DoRA는 Zotero 동기화로, VeRA는 주제 수집으로 들어온다.
// 상태는 메모리에만 있어서 새로고침하면 처음으로 돌아간다.
//
// 계정(비밀번호는 아무 값): minsu(개발팀 팀원 L1) · admin(개발팀 관리자 L3) · rnd(R&D팀 관리자, 빈 라이브러리) · noteam(팀 없음) · fail(실패)
// 초대 코드: K3F9Q2XA(플랫폼개발팀), R7M2PQ4C(선행연구팀)
// 질문으로 시나리오 고르기(/rag-query):
//   기본 → LoRA 답변(출처 2개) / "어텐션"·"수식" → needs_review / "DoRA"·"VeRA"(라이브러리에 없을 때)·"없는" → handoff
//   "503" → NOT_READY / "타임아웃" → UPSTREAM_TIMEOUT / "401" → TOKEN_EXPIRED / "느린" → 12초 지연 / "xss" → sanitize 확인
// PDF 이름: dup → 409, scan → 배치에서 "텍스트 추출 불가(스캔 PDF)"로 실패. 주제 검색어 zzz → 후보 0건.
import { decodeJwt, isExpired } from '@/lib/jwt'

const wait = (ms, signal) =>
  new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(signal.reason ?? new DOMException('aborted', 'AbortError'))
      },
      { once: true },
    )
  })

const between = (min, max) => Math.round(min + Math.random() * (max - min))
const daysAgo = (n) => new Date(Date.now() - n * 86_400_000).toISOString()

function respond(status, body) {
  if (body instanceof Blob) return new Response(body, { status, headers: { 'Content-Type': body.type } })
  return new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function base64url(obj) {
  let binary = ''
  new TextEncoder().encode(JSON.stringify(obj)).forEach((b) => (binary += String.fromCharCode(b)))
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

const javaError = (status, code, error) => [status, { ok: false, error, code }]
const aiError = (status, code, detail, extra = {}) => [status, { detail, code, ...extra }]

// ---------- 인증 (DEV_01 4절) ----------
const TEAMS = new Map([
  [3, { id: 3, name: '플랫폼개발팀', type: 'dev', inviteCode: 'K3F9Q2XA' }],
  [4, { id: 4, name: '선행연구팀', type: 'rnd', inviteCode: 'R7M2PQ4C' }],
])

const users = new Map()
let userSeq = 20

function addUser({ username, displayName, role = 'member', level = 'L2', view = null, teamId = null }) {
  const team = TEAMS.get(teamId)
  const user = { id: ++userSeq, username, displayName: displayName || username, role, level, view: view ?? team?.type ?? 'dev', teamId }
  users.set(username, user)
  return user
}

addUser({ username: 'minsu', displayName: '민수', level: 'L1', teamId: 3 })
addUser({ username: 'admin', displayName: '지원', role: 'team_admin', level: 'L3', teamId: 3 })
addUser({ username: 'rnd', displayName: '서준', role: 'team_admin', level: 'L3', teamId: 4 })
addUser({ username: 'noteam', displayName: '서연', level: 'L2' })

const teamView = (team) => (team ? { id: team.id, name: team.name, type: team.type } : null)

function publicUser(u) {
  return { id: u.id, username: u.username, displayName: u.displayName, role: u.role, level: u.level, view: u.view, team: teamView(TEAMS.get(u.teamId)) }
}

function issueToken(u) {
  const now = Math.floor(Date.now() / 1000)
  const team = TEAMS.get(u.teamId)
  const claims = {
    iss: 'simple-auth-server',
    sub: String(u.id),
    username: u.username,
    role: u.role,
    team_id: team?.id ?? null,
    team_type: team?.type ?? null,
    level: u.level,
    view: u.view,
    iat: now,
    exp: now + 3600,
  }
  return [base64url({ alg: 'none', typ: 'JWT' }), base64url(claims), 'mock'].join('.')
}

const session = (u) => ({ ok: true, accessToken: issueToken(u), tokenType: 'Bearer', expiresIn: 3600, user: publicUser(u) })
const userOf = (claims) => [...users.values()].find((u) => String(u.id) === claims?.sub) ?? null
const teamByCode = (code) => [...TEAMS.values()].find((t) => t.inviteCode === String(code ?? '').toUpperCase())

function login({ body }) {
  const username = String(body?.username ?? '').trim()
  if (!username || !body?.password || username === 'fail') return javaError(401, 'INVALID_CREDENTIALS', 'invalid credentials')
  const user = users.get(username) ?? addUser({ username, teamId: 3 })
  return [200, session(user)]
}

function signup({ body }) {
  const { username, password, displayName, level, teamMode, teamName, teamType, teamCode } = body ?? {}
  if (!username || username.length < 4 || username.length > 50 || !password || password.length < 8)
    return javaError(422, 'VALIDATION_ERROR', 'invalid input')
  if (users.has(username)) return javaError(409, 'CONFLICT', 'username exists')
  if (teamMode === 'join') {
    const team = teamByCode(teamCode)
    if (!team) return javaError(404, 'TEAM_NOT_FOUND', 'team not found')
    addUser({ username, displayName, level, teamId: team.id })
    return [201, { ok: true, teamId: team.id, role: 'member' }]
  }
  if (teamMode === 'create') {
    const id = Math.max(...TEAMS.keys()) + 1
    const inviteCode = Math.random().toString(36).slice(2, 10).toUpperCase().padEnd(8, 'X')
    TEAMS.set(id, { id, name: teamName, type: teamType, inviteCode })
    addUser({ username, displayName, level, role: 'team_admin', teamId: id })
    return [201, { ok: true, teamId: id, role: 'team_admin', inviteCode }]
  }
  addUser({ username, displayName, level })
  return [201, { ok: true, teamId: null, role: 'member' }]
}

function me({ claims }) {
  const user = userOf(claims)
  return user ? [200, { user: publicUser(user) }] : javaError(401, 'UNAUTHORIZED', 'unknown user')
}

function updateProfile({ body, claims }) {
  const user = userOf(claims)
  if (!user) return javaError(401, 'UNAUTHORIZED', 'unknown user')
  if (body?.level && !['L1', 'L2', 'L3'].includes(body.level)) return javaError(422, 'VALIDATION_ERROR', 'level')
  if (body?.view && !['dev', 'rnd'].includes(body.view)) return javaError(422, 'VALIDATION_ERROR', 'view')
  Object.assign(user, { level: body?.level ?? user.level, view: body?.view ?? user.view })
  return [200, session(user)]
}

function getTeam({ claims }) {
  const team = TEAMS.get(claims?.team_id)
  if (!team) return javaError(403, 'NO_TEAM', 'no team')
  const memberCount = [...users.values()].filter((u) => u.teamId === team.id).length
  const { inviteCode, ...rest } = team
  return [200, { ok: true, team: claims.role === 'team_admin' ? { ...team, memberCount } : { ...rest, memberCount } }]
}

function joinTeam({ body, claims }) {
  const user = userOf(claims)
  if (!user) return javaError(401, 'UNAUTHORIZED', 'unknown user')
  if (user.teamId) return javaError(409, 'ALREADY_IN_TEAM', 'already in team')
  const team = teamByCode(body?.teamCode)
  if (!team) return javaError(404, 'TEAM_NOT_FOUND', 'team not found')
  Object.assign(user, { teamId: team.id, view: team.type })
  return [200, session(user)]
}

// ---------- 라이브러리 (DEV_03 5절) ----------
// 행 모양은 GET /papers 예시 + rag_papers 컬럼(error_msg, added_by, arxiv_id)
const papers = [
  { id: 41, team_id: 3, title: 'LoRA: Low-Rank Adaptation of Large Language Models', authors: 'Edward J. Hu, Yelong Shen, Phillip Wallis', year: 2021, source_type: 'zotero', tags: ['peft', 'lora'], status: 'indexed', chunk_count: 96, url: 'https://arxiv.org/abs/2106.09685', arxiv_id: '2106.09685', created_at: daysAgo(6), added_by: '22' },
  { id: 42, team_id: 3, title: 'QLoRA: Efficient Finetuning of Quantized LLMs', authors: 'Tim Dettmers, Artidoro Pagnoni, Ari Holtzman', year: 2023, source_type: 'zotero', tags: ['peft', 'quantization'], status: 'indexed', chunk_count: 118, url: 'https://arxiv.org/abs/2305.14314', arxiv_id: '2305.14314', created_at: daysAgo(6), added_by: '22' },
  { id: 43, team_id: 3, title: 'Attention Is All You Need', authors: 'Ashish Vaswani, Noam Shazeer, Niki Parmar', year: 2017, source_type: 'zotero', tags: ['transformer'], status: 'indexed', chunk_count: 64, url: 'https://arxiv.org/abs/1706.03762', arxiv_id: '1706.03762', created_at: daysAgo(9), added_by: '22' },
  { id: 44, team_id: 3, title: 'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks', authors: 'Patrick Lewis, Ethan Perez, Aleksandra Piktus', year: 2020, source_type: 'pdf', tags: ['rag'], status: 'indexed', chunk_count: 52, url: null, arxiv_id: '2005.11401', created_at: daysAgo(3), added_by: '21' },
  { id: 45, team_id: 3, title: 'Chain-of-Thought Prompting Elicits Reasoning in Large Language Models', authors: 'Jason Wei, Xuezhi Wang, Dale Schuurmans', year: 2022, source_type: 'zotero', tags: ['prompting'], status: 'pending', chunk_count: null, url: 'https://arxiv.org/abs/2201.11903', arxiv_id: '2201.11903', created_at: daysAgo(0), added_by: '22' },
  { id: 46, team_id: 3, title: 'Robust Speech Recognition via Large-Scale Weak Supervision', authors: 'Alec Radford, Jong Wook Kim, Tao Xu', year: 2022, source_type: 'zotero', tags: ['speech'], status: 'failed', error_msg: 'PDF 첨부 없음', chunk_count: null, url: null, arxiv_id: '2212.04356', created_at: daysAgo(1), added_by: '22' },
]
let paperSeq = 100

const zotero = new Map([[3, { group_id: 5481123, last_synced_at: daysAgo(1) }]]) // team_id → 설정

const teamPapers = (claims) => papers.filter((p) => p.team_id === claims.team_id)
const inLibrary = (claims, arxivId) => teamPapers(claims).some((p) => p.arxiv_id === arxivId && p.status !== 'failed')

function stats({ claims }) {
  const mine = teamPapers(claims)
  const chunks = (type) => mine.filter((p) => p.source_type === type).reduce((n, p) => n + (p.chunk_count ?? 0), 0)
  return [
    200,
    {
      papers: mine.length,
      indexed: mine.filter((p) => p.status === 'indexed').length,
      failed: mine.filter((p) => p.status === 'failed').length,
      chunks: { pdf: chunks('pdf') + chunks('zotero'), web: chunks('web'), annotation: 0 },
      last_synced_at: zotero.get(claims.team_id)?.last_synced_at ?? null,
    },
  ]
}

function publicPaper({ team_id, arxiv_id, ...rest }) {
  return rest
}

function listPapers({ query, claims }) {
  const q = (query.get('q') ?? '').toLowerCase()
  const filtered = teamPapers(claims).filter(
    (p) =>
      (!q || p.title.toLowerCase().includes(q)) &&
      (!query.get('source_type') || p.source_type === query.get('source_type')) &&
      (!query.get('tag') || p.tags.includes(query.get('tag'))) &&
      (!query.get('status') || p.status === query.get('status')),
  )
  const page = Math.max(1, Number(query.get('page') ?? 1))
  const size = Math.max(1, Number(query.get('size') ?? 20))
  return [200, { total: filtered.length, items: filtered.slice((page - 1) * size, page * size).map(publicPaper) }]
}

const findPaper = (claims, id) => teamPapers(claims).find((p) => String(p.id) === String(id))

function getPaper({ params, claims }) {
  const paper = findPaper(claims, params.id)
  return paper ? [200, publicPaper(paper)] : aiError(404, 'NOT_FOUND', '논문을 찾을 수 없습니다.')
}

// 원문 PDF: GET /papers/{id}/pdf (문서에 없는 경로라 백엔드에 추가 요청). 목업은 쪽 번호가 보이는 PDF를 만들어 준다.
// arXiv에서 수집한 논문(web)은 없는 것으로 돌려줘서 화면이 arXiv 원문으로 넘어가는 경로를 확인할 수 있게 한다.
function getPaperPdf({ params, claims }) {
  const paper = findPaper(claims, params.id)
  if (!paper || paper.source_type === 'web') return aiError(404, 'NOT_FOUND', '원문 파일이 없습니다.')
  return [200, mockPdf(paper.title, 12), between(300, 800)]
}

// 글꼴 내장 없이 Helvetica로 쓰는 아주 작은 PDF. 영문만 넣는다(쪽마다 제목과 쪽 번호).
function mockPdf(title, pages) {
  const esc = (t) => String(t).replace(/[^\x20-\x7e]/g, '?').replace(/([()\\])/g, '\\$1')
  const objs = ['<< /Type /Catalog /Pages 2 0 R >>', null, '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
  const kids = []
  for (let n = 1; n <= pages; n++) {
    const text = [
      `BT /F1 11 Tf 56 780 Td (${esc(title).slice(0, 80)}) Tj ET`,
      `BT /F1 40 Tf 56 700 Td (Page ${n}) Tj ET`,
      `BT /F1 11 Tf 56 660 Td (Mock PDF for Referoom. The real file comes from GET /papers/{id}/pdf.) Tj ET`,
    ].join('\n')
    objs.push(`<< /Length ${text.length} >>\nstream\n${text}\nendstream`)
    const contentRef = objs.length
    objs.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents ${contentRef} 0 R >>`)
    kids.push(`${objs.length} 0 R`)
  }
  objs[1] = `<< /Type /Pages /Kids [${kids.join(' ')}] /Count ${pages} >>`
  let out = '%PDF-1.4\n'
  const offsets = objs.map((body, i) => {
    const at = out.length
    out += `${i + 1} 0 obj\n${body}\nendobj\n`
    return at
  })
  const xref = out.length
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`).join('')}`
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`
  return new Blob([out], { type: 'application/pdf' })
}

function deletePaper({ params, claims }) {
  const paper = findPaper(claims, params.id)
  if (!paper) return aiError(404, 'NOT_FOUND', '논문을 찾을 수 없습니다.')
  if (claims.role !== 'team_admin' && paper.added_by !== claims.sub) return aiError(403, 'FORBIDDEN', 'not allowed')
  papers.splice(papers.indexOf(paper), 1)
  return [204, null]
}

// 배치: 논문 행은 접수 즉시 pending으로 생기고, 폴링할 때마다 한 편씩 끝난다(DEV_03 3.1·3.3).
const batches = new Map()
let batchSeq = 10

function createBatch(claims, kind, query, entries) {
  const id = ++batchSeq
  const rows = entries.map((e) => {
    const row = { id: ++paperSeq, team_id: claims.team_id, source_type: 'pdf', tags: [], status: 'pending', chunk_count: null, url: null, created_at: new Date().toISOString(), added_by: claims.sub, ...e.paper }
    papers.unshift(row)
    return { row, failWith: e.failWith }
  })
  batches.set(id, { id, team_id: claims.team_id, kind, query, polls: 0, status: 'running', rows, onDone: null })
  return batches.get(id)
}

function batchView(batch) {
  const rows = batch.rows
  return {
    id: batch.id,
    kind: batch.kind,
    status: batch.status,
    requested: rows.length,
    indexed: rows.filter((r) => r.row.status === 'indexed').length,
    skipped: 0,
    failed: rows.filter((r) => r.row.status === 'failed').length,
    papers: rows.map(({ row }) => ({ paper_id: row.id, title: row.title, status: row.status, chunk_count: row.chunk_count ?? undefined, error_msg: row.error_msg })),
  }
}

function getBatch({ params, claims }) {
  const batch = batches.get(Number(params.id))
  if (!batch || batch.team_id !== claims.team_id) return aiError(404, 'NOT_FOUND', '배치를 찾을 수 없습니다.')
  if (batch.status === 'running') {
    batch.polls += 1
    batch.rows.forEach(({ row, failWith }, i) => {
      if (i < batch.polls - 1 && row.status === 'pending') {
        if (failWith) Object.assign(row, { status: 'failed', error_msg: failWith })
        else Object.assign(row, { status: 'indexed', chunk_count: between(40, 140) })
      }
    })
    if (batch.rows.every(({ row }) => row.status !== 'pending')) {
      batch.status = batch.rows.some(({ row }) => row.status === 'indexed') ? 'done' : 'failed'
      batch.onDone?.()
    }
  }
  return [200, batchView(batch)]
}

function rollbackBatch({ params, claims }) {
  if (claims.role !== 'team_admin') return aiError(403, 'FORBIDDEN', 'admin only')
  const batch = batches.get(Number(params.id))
  if (!batch || batch.team_id !== claims.team_id) return aiError(404, 'NOT_FOUND', '배치를 찾을 수 없습니다.')
  batch.rows.forEach(({ row }) => papers.includes(row) && papers.splice(papers.indexOf(row), 1))
  batch.status = 'rolled_back'
  return [200, { ok: true, ...batchView(batch) }]
}

function uploadPaper({ formData, claims }) {
  const file = formData?.get('file')
  const name = String(file?.name ?? '')
  if (!name.toLowerCase().endsWith('.pdf')) return aiError(422, 'VALIDATION_ERROR', 'PDF 파일만 올릴 수 있습니다.')
  if (file.size > 20 * 1024 * 1024) return aiError(413, 'PAYLOAD_TOO_LARGE', '20MB를 넘었습니다.')
  const title = name.replace(/\.pdf$/i, '')
  const dup = teamPapers(claims).find((p) => p.title === title)
  if (/dup/i.test(name) || dup) return aiError(409, 'CONFLICT', '이미 등록된 논문입니다.', { paper_id: dup?.id ?? 41 })
  const tags = String(formData.get('tags') ?? '').split(',').map((t) => t.trim()).filter(Boolean)
  const batch = createBatch(claims, 'upload_pdf', null, [
    { paper: { title, authors: '', year: null, source_type: 'pdf', tags }, failWith: /scan/i.test(name) ? '텍스트 추출 불가(스캔 PDF)' : null },
  ])
  return [202, { batch_id: batch.id, paper_id: batch.rows[0].row.id, status: 'pending' }]
}

const CANDIDATES = [
  { candidate_id: '2310.11454', title: 'VeRA: Vector-based Random Matrix Adaptation', authors: ['Dawid J. Kopiczko', 'Tijmen Blankevoort', 'Yuki M. Asano'], year: 2023, abstract: '층마다 공유하는 무작위 행렬은 고정하고, 작은 스케일 벡터만 학습해 LoRA보다 학습 파라미터를 더 줄이는 방법.', relevance: 0.91 },
  { candidate_id: '2402.12354', title: 'LoRA+: Efficient Low Rank Adaptation of Large Models', authors: ['Soufiane Hayou', 'Nikhil Ghosh', 'Bin Yu'], year: 2024, abstract: 'LoRA의 두 행렬 A와 B에 서로 다른 학습률을 주면 학습이 더 빨라진다는 분석.', relevance: 0.78 },
  { candidate_id: '2106.09685', title: 'LoRA: Low-Rank Adaptation of Large Language Models', authors: ['Edward J. Hu', 'Yelong Shen'], year: 2021, abstract: '사전학습 가중치는 고정하고 저랭크 분해 행렬만 학습하는 미세조정 방법.', relevance: 0.74 },
  { candidate_id: '2303.10512', title: 'AdaLoRA: Adaptive Budget Allocation for Parameter-Efficient Fine-Tuning', authors: ['Qingru Zhang', 'Minshuo Chen'], year: 2023, abstract: '층마다 중요도에 따라 LoRA 랭크를 다르게 배분하는 방법.', relevance: 0.69 },
  { candidate_id: '2001.08361', title: 'Scaling Laws for Neural Language Models', authors: ['Jared Kaplan', 'Sam McCandlish'], year: 2020, abstract: '모델 크기, 데이터, 연산량에 따른 언어 모델 손실의 거듭제곱 법칙.', relevance: 0.31 },
]
const MIN_RELEVANCE = 0.45 // TOPIC_MIN_RELEVANCE

const candidatesFor = (claims) =>
  CANDIDATES.map((c) => ({
    ...c,
    url: `https://arxiv.org/abs/${c.candidate_id}`,
    pdf_url: `https://arxiv.org/pdf/${c.candidate_id}`,
    low_relevance: c.relevance < MIN_RELEVANCE,
    already_in_library: inLibrary(claims, c.candidate_id),
  }))

function searchTopic({ body, claims }) {
  const topic = String(body?.topic ?? '').trim()
  if (topic.length < 2) return aiError(422, 'VALIDATION_ERROR', '주제를 입력하세요.')
  if (/^z+$/i.test(topic)) return [200, { topic, candidates: [] }]
  return [200, { topic, candidates: candidatesFor(claims).slice(0, body.max_results ?? 10) }]
}

function uploadTopic({ body, claims }) {
  const topic = String(body?.topic ?? '').trim()
  const pool = candidatesFor(claims).filter((c) => !c.already_in_library)
  // selected가 없으면 자동 선택: 관련도 상위, low_relevance 제외, 최대 5건(DEV_03 5.1)
  const picked = Array.isArray(body?.selected)
    ? pool.filter((c) => body.selected.includes(c.candidate_id))
    : pool.filter((c) => !c.low_relevance).slice(0, 5)
  if (picked.length === 0 || picked.length > 5) return aiError(422, 'VALIDATION_ERROR', '1~5편을 고르세요.')
  const batch = createBatch(
    claims,
    'topic',
    topic,
    picked.map((c) => ({ paper: { title: c.title, authors: c.authors.join(', '), year: c.year, source_type: 'web', url: c.url, arxiv_id: c.candidate_id } })),
  )
  return [202, { batch_id: batch.id, requested: picked.length }]
}

function getZoteroConfig({ claims }) {
  const cfg = zotero.get(claims.team_id)
  return [200, { configured: Boolean(cfg), group_id: cfg?.group_id ?? null, last_synced_at: cfg?.last_synced_at ?? null }]
}

function saveZoteroConfig({ body, claims }) {
  const groupId = Number(body?.group_id)
  if (!Number.isInteger(groupId) || groupId <= 0 || String(body?.api_key ?? '').length < 10)
    return aiError(400, 'ZOTERO_AUTH_FAILED', 'Zotero 연결 실패')
  zotero.set(claims.team_id, { group_id: groupId, last_synced_at: zotero.get(claims.team_id)?.last_synced_at ?? null })
  return [200, { ok: true }]
}

function deleteZoteroConfig({ claims }) {
  zotero.delete(claims.team_id)
  return [200, { ok: true }]
}

function syncZotero({ claims }) {
  const cfg = zotero.get(claims.team_id)
  if (!cfg) return aiError(400, 'ZOTERO_AUTH_FAILED', '연동 설정이 없습니다.')
  // 시연(DEV_05 5.1): 관리자가 Zotero 그룹에 DoRA를 추가한 뒤 동기화한다
  const entries = []
  if (!inLibrary(claims, '2402.09353'))
    entries.push({ paper: { title: 'DoRA: Weight-Decomposed Low-Rank Adaptation', authors: 'Shih-Yang Liu, Chien-Yi Wang, Hongxu Yin', year: 2024, source_type: 'zotero', tags: ['peft', 'lora'], url: 'https://arxiv.org/abs/2402.09353', arxiv_id: '2402.09353' } })
  entries.push({ paper: { title: 'Training language models to follow instructions with human feedback', authors: 'Long Ouyang, Jeff Wu', year: 2022, source_type: 'zotero', tags: ['rlhf'] }, failWith: 'PDF 첨부 없음' })
  const batch = createBatch(claims, 'zotero_sync', null, entries)
  batch.onDone = () => (cfg.last_synced_at = new Date().toISOString())
  return [202, { batch_id: batch.id }]
}

// ---------- 질의 (DEV_04 2절) ----------
const detail = (paperId, label, page, snippet) => {
  const p = papers.find((x) => x.id === paperId)
  return { label, paper_id: paperId, title: p?.title ?? '', page, url: p?.url ?? null, snippet }
}
const sourcesOf = (details) => [...new Set(details.map((d) => `${d.title} p.${d.page}`))]

const LORA_BY_LEVEL = {
  L1: 'LoRA는 거대한 모델을 통째로 다시 학습하지 않고, 원래 가중치는 그대로 둔 채 작은 부품만 새로 학습하는 방법이에요 [S1].\n\n두꺼운 전공책을 고쳐 쓰는 대신 얇은 메모지를 끼워 넣는다고 생각하면 쉬워요. 원래 가중치 W는 얼려 두고, 바뀌는 양을 작은 행렬 두 개(B와 A)의 곱으로만 표현해서 그 두 개만 학습해요 [S1].\n\n**핵심 한 줄:** 큰 모델은 그대로 두고 작은 행렬 두 개만 학습한다.',
  L2: 'LoRA는 사전학습 가중치 $W_0$를 고정하고, 업데이트 $\\Delta W$를 랭크 $r$인 두 행렬의 곱 $BA$로 제한해 그 부분만 학습합니다 [S1].\n\n- 학습 대상: 주로 어텐션의 $W_q$, $W_v$에 붙인 $A \\in \\mathbb{R}^{r \\times k}$, $B \\in \\mathbb{R}^{d \\times r}$\n- 하이퍼파라미터: 랭크 $r$(보통 1~8), 스케일 $\\alpha$\n- 초기화: $A$는 무작위, $B$는 0이라 학습 시작 시 $\\Delta W = 0$ [S1]',
  L3: 'LoRA는 적응에 필요한 가중치 변화가 낮은 내재 랭크(intrinsic rank)를 가진다는 가정에서 출발합니다 [S1]. 업데이트를 $\\Delta W = BA$ ($r \\ll \\min(d, k)$)로 제한하면 학습 파라미터는 $r(d + k)$개로 줄어듭니다.\n\n한계도 있습니다. 랭크가 너무 낮으면 표현력이 부족할 수 있고, 어느 층에 붙일지와 $r$은 실험으로 정해야 합니다 [S2].',
}
const LORA_BY_VIEW = {
  dev: '구현할 때는 작업마다 B와 A만 어댑터 파일로 저장하면 되고, 배포 전에 W₀ + BA를 미리 합쳐 두면 추론 지연이 늘지 않아요 [S2].',
  rnd: '연구 관점에서 핵심 주장은 전체 미세조정과 비슷한 성능을 훨씬 적은 학습 파라미터로 낸다는 점이고, 배포 시 지연이 없다는 점이 기존 어댑터 방식과의 차이입니다 [S2].',
}

function ragQuery({ body, claims }) {
  const question = String(body?.question ?? '').trim()
  if (question.length < 2 || question.length > 1000) return aiError(422, 'VALIDATION_ERROR', '질문은 2~1000자여야 합니다.')
  if (question.includes('503')) return aiError(503, 'NOT_READY', '인덱스 준비 중')
  if (question.includes('타임아웃')) return aiError(503, 'UPSTREAM_TIMEOUT', 'LLM timeout')
  if (question.includes('401')) return aiError(401, 'TOKEN_EXPIRED', '토큰 만료')

  const level = body.level ?? claims.level ?? 'L2'
  const view = body.view ?? claims.view ?? 'dev'
  const delay = question.includes('느린') ? 12_000 : between(1500, 3000)
  const meta = { level, view, latency_ms: delay }
  const handoff = [200, { ...meta, answer: '팀 라이브러리에서 관련 내용을 찾을 수 없습니다.', sources: [], source_details: [], needs_review: false, handoff: true }, delay]

  if (teamPapers(claims).every((p) => p.status !== 'indexed') || /없는/.test(question)) return handoff
  if (/dora/i.test(question)) {
    if (!inLibrary(claims, '2402.09353')) return handoff
    const dora = papers.find((p) => p.arxiv_id === '2402.09353' && p.team_id === claims.team_id)
    const details = [detail(dora.id, 'S1', 3, '가중치를 크기(magnitude)와 방향(direction)으로 나누고, 방향에만 LoRA를 적용한다.'), detail(41, 'S2', 4, '사전학습 가중치는 고정하고 저랭크 행렬 B, A만 학습한다.')]
    const answer = 'DoRA는 가중치를 크기와 방향 두 부분으로 나눈 뒤, 방향 쪽에만 LoRA를 적용하고 크기는 따로 학습합니다 [S1]. LoRA는 가중치 변화 전체를 저랭크 행렬 BA 하나로 표현한다는 점이 다릅니다 [S2].'
    return [200, { ...meta, answer, sources: sourcesOf(details), source_details: details, needs_review: false, handoff: false }, delay]
  }
  if (/vera/i.test(question)) {
    const vera = teamPapers(claims).find((p) => p.arxiv_id === '2310.11454' && p.status === 'indexed')
    if (!vera) return handoff
    const details = [detail(vera.id, 'S1', 2, '무작위로 초기화한 행렬 한 쌍을 모든 층이 공유하고 고정한다. 학습하는 것은 층별 스케일 벡터뿐이다.')]
    return [200, { ...meta, answer: 'VeRA는 모든 층이 공유하는 무작위 행렬은 고정하고, 층마다 작은 스케일 벡터만 학습합니다 [S1].', sources: sourcesOf(details), source_details: details, needs_review: false, handoff: false }, delay]
  }
  if (/xss/i.test(question)) {
    const details = [detail(41, 'S1', 4, '사전학습 가중치는 고정한다.')]
    const answer = 'sanitize 확인용 응답입니다 [S1]. <script>alert("xss")</script> <img src=x onerror="alert(1)"> [링크](javascript:alert(1))'
    return [200, { ...meta, answer, sources: sourcesOf(details), source_details: details, needs_review: false, handoff: false }, delay]
  }
  if (/어텐션|attention|softmax|수식|d_k/i.test(question)) {
    const details = [detail(43, 'S1', 4, '3.2.1절. 쿼리와 키의 내적을 √d_k로 나눈 뒤 softmax로 가중치를 구한다.'), detail(43, 'S2', 4, '각주. d_k가 크면 내적 값의 분산이 커져 softmax가 기울기가 매우 작은 영역으로 밀린다.')]
    const intro = level === 'L1' ? '쉽게 말해, 점수가 너무 커지면 모델이 한 단어에만 쏠려서 제대로 배우지 못하니 점수의 크기를 줄여 주는 장치예요 [S1].\n\n' : ''
    const answer = `${intro}Scaled dot-product attention은 쿼리와 키의 내적을 $\\sqrt{d_k}$로 나눈 뒤 softmax를 적용합니다 [S1].\n\n$$\\mathrm{Attention}(Q, K, V) = \\mathrm{softmax}\\left(\\frac{QK^\\top}{\\sqrt{d_k}}\\right)V$$\n\n$d_k$가 커질수록 내적 값의 분산도 커져서 softmax 출력이 한쪽으로 쏠리고, 기울기가 아주 작아집니다. $\\sqrt{d_k}$로 나누는 것은 이 현상을 막기 위한 조정입니다 [S2].`
    return [200, { ...meta, answer, sources: sourcesOf(details), source_details: details, needs_review: true, handoff: false }, delay]
  }
  const details = [
    detail(41, 'S1', 4, '사전학습 가중치 W₀는 고정하고, 업데이트를 랭크 r인 두 행렬 B, A의 곱으로 제한해 그 부분만 학습한다.'),
    detail(41, 'S2', 5, '배포할 때 W = W₀ + BA를 미리 계산해 두면 추론 지연이 추가로 생기지 않는다.'),
  ]
  const answer = `${LORA_BY_LEVEL[level] ?? LORA_BY_LEVEL.L2}\n\n${LORA_BY_VIEW[view] ?? LORA_BY_VIEW.dev}`
  return [200, { ...meta, answer, sources: sourcesOf(details), source_details: details, needs_review: false, handoff: false }, delay]
}

function summary({ body, claims }) {
  const paper = findPaper(claims, body?.paper_id)
  if (!paper) return aiError(404, 'NOT_FOUND', '논문을 찾을 수 없습니다.')
  const view = body.view ?? 'dev'
  const src = (page) => [`${paper.title} p.${page}`]
  const sections = [
    { key: 'problem', title: '문제', text: '이 논문이 풀려는 문제를 정리한 목업 문단입니다. 기존 방법의 비용과 한계를 짚습니다.', sources: src(1) },
    { key: 'idea', title: '핵심 아이디어', text: '핵심 아이디어를 한두 문장으로 정리한 목업 문단입니다.', sources: src(2) },
    { key: 'method', title: '방법', text: '- 입력과 출력\n- 학습 대상\n- 주요 하이퍼파라미터', sources: src(3) },
    { key: 'result', title: '결과', text: '주요 실험 결과를 비교한 목업 문단입니다. 수치는 원문에서 확인하세요.', sources: src(8) },
    { key: 'limit', title: '한계', text: '논문에서 찾을 수 없음', sources: [] },
    view === 'rnd'
      ? { key: 'check', title: '선행연구 비교·재현성', text: '기존 방법과의 차이, 재현에 필요한 설정을 정리한 목업 문단입니다.', sources: src(6) }
      : { key: 'check', title: '구현 시 체크포인트', text: '1. 어디에 붙일지 정한다\n2. 하이퍼파라미터 기본값으로 시작한다\n3. 평가셋으로 비교한다', sources: src(6) },
  ]
  return [200, { paper_id: paper.id, title: paper.title, level: body.level ?? 'L2', view, sections, needs_review: true, latency_ms: 9100 }, between(2000, 3000)]
}

// ---------- 음성 (DEV_04 6.2) ----------
const audios = new Map() // audio_id → owner sub

function silentWav(seconds = 0.6, rate = 8000) {
  const samples = Math.round(seconds * rate)
  const buf = new DataView(new ArrayBuffer(44 + samples))
  const text = (o, s) => [...s].forEach((c, i) => buf.setUint8(o + i, c.charCodeAt(0)))
  text(0, 'RIFF'); buf.setUint32(4, 36 + samples, true); text(8, 'WAVEfmt ')
  buf.setUint32(16, 16, true); buf.setUint16(20, 1, true); buf.setUint16(22, 1, true)
  buf.setUint32(24, rate, true); buf.setUint32(28, rate, true); buf.setUint16(32, 1, true); buf.setUint16(34, 8, true)
  text(36, 'data'); buf.setUint32(40, samples, true)
  for (let i = 0; i < samples; i++) buf.setUint8(44 + i, 128)
  return new Blob([buf], { type: 'audio/wav' })
}

function newAudio(claims) {
  const id = Math.random().toString(16).slice(2, 10)
  audios.set(id, claims.sub)
  return { audio_id: id, audio_url: `/audio/${id}` }
}

function stt({ formData }) {
  const audio = formData?.get('audio')
  if (!audio || audio.size === 0) return aiError(422, 'STT_EMPTY', '음성을 인식하지 못했어요. 다시 말씀해 주세요.')
  return [200, { text: 'LoRA는 어떤 파라미터를 학습해?', language: String(formData.get('language') ?? 'ko'), duration_s: 4.2, latency_ms: 1200 }]
}

function tts({ body, claims }) {
  if (!String(body?.text ?? '').trim()) return aiError(422, 'VALIDATION_ERROR', '읽을 텍스트가 없습니다.')
  return [200, { ...newAudio(claims), latency_ms: 900 }]
}

function voiceQa({ formData, claims }) {
  const audio = formData?.get('audio')
  if (!audio || audio.size === 0) return aiError(422, 'STT_EMPTY', '음성을 인식하지 못했어요. 다시 말씀해 주세요.')
  const [status, rag] = ragQuery({ body: { question: 'LoRA는 어떤 파라미터를 학습해?', level: formData.get('level'), view: formData.get('view') }, claims })
  if (status !== 200) return [status, rag]
  const speech = rag.handoff ? '논문 라이브러리에서 관련 내용을 찾지 못했어요. 논문 추가를 요청해 보세요.' : '사전학습 가중치는 고정하고 저랭크 행렬만 학습합니다. 자세한 내용은 화면을 확인하세요.'
  return [200, { stt_text: 'LoRA는 어떤 파라미터를 학습해?', ...rag, speech_text: speech, ...newAudio(claims), latency_ms: { stt: 1200, rag: rag.latency_ms, tts: 900, total: 2100 + rag.latency_ms } }, 3000]
}

function getAudio({ params, claims }) {
  if (audios.get(params.id) !== claims.sub) return aiError(404, 'NOT_FOUND', 'not found')
  return [200, silentWav()]
}

// ---------- 라우팅 ----------
// [메서드, 서비스, 경로, 처리 함수, 접근('none' | 'login' | 'team' | 'admin')]
const ROUTES = [
  ['POST', 'auth', /^\/api\/login$/, login, 'none'],
  ['POST', 'auth', /^\/api\/signup$/, signup, 'none'],
  ['POST', 'auth', /^\/api\/logout$/, () => [200, { ok: true }], 'none'],
  ['GET', 'auth', /^\/api\/me$/, me, 'login'],
  ['PATCH', 'auth', /^\/api\/me\/profile$/, updateProfile, 'login'],
  ['GET', 'auth', /^\/api\/team$/, getTeam, 'login'],
  ['POST', 'auth', /^\/api\/team\/join$/, joinTeam, 'login'],
  ['GET', 'auth', /^\/api\/health$/, () => [200, { ok: true, db: 'up' }], 'none'],

  ['GET', 'rag', /^\/library\/stats$/, stats, 'team'],
  ['GET', 'rag', /^\/papers$/, listPapers, 'team'],
  ['GET', 'rag', /^\/papers\/(?<id>[^/]+)$/, getPaper, 'team'],
  ['GET', 'rag', /^\/papers\/(?<id>[^/]+)\/pdf$/, getPaperPdf, 'team'],
  ['DELETE', 'rag', /^\/papers\/(?<id>[^/]+)$/, deletePaper, 'team'],
  ['POST', 'rag', /^\/upload-paper$/, uploadPaper, 'team'],
  ['POST', 'rag', /^\/search-topic$/, searchTopic, 'team'],
  ['POST', 'rag', /^\/upload-topic$/, uploadTopic, 'team'],
  ['GET', 'rag', /^\/ingest\/batches\/(?<id>[^/]+)$/, getBatch, 'team'],
  ['POST', 'rag', /^\/ingest\/batches\/(?<id>[^/]+)\/rollback$/, rollbackBatch, 'admin'],
  ['GET', 'rag', /^\/zotero\/config$/, getZoteroConfig, 'admin'],
  ['POST', 'rag', /^\/zotero\/config$/, saveZoteroConfig, 'admin'],
  ['DELETE', 'rag', /^\/zotero\/config$/, deleteZoteroConfig, 'admin'],
  ['POST', 'rag', /^\/zotero\/sync$/, syncZotero, 'admin'],
  ['POST', 'rag', /^\/rag-query$/, ragQuery, 'team'],
  ['POST', 'rag', /^\/summary$/, summary, 'team'],
  ['GET', 'rag', /^\/health$/, () => [200, { status: 'ok' }], 'none'],

  ['POST', 'voice', /^\/stt$/, stt, 'team'],
  ['POST', 'voice', /^\/tts$/, tts, 'team'],
  ['POST', 'voice', /^\/voice-qa$/, voiceQa, 'team'],
  ['GET', 'voice', /^\/audio\/(?<id>[^/]+)$/, getAudio, 'team'],
  ['GET', 'voice', /^\/health$/, () => [200, { status: 'ok' }], 'none'],
]

export async function mockFetch(url, init, baseUrl) {
  const service = Object.keys(baseUrl).find((key) => new URL(baseUrl[key]).origin === url.origin)
  const method = init.method ?? 'GET'
  const route = ROUTES.find(([m, s, pattern]) => m === method && s === service && pattern.test(url.pathname))
  if (!route) {
    await wait(300, init.signal)
    return respond(404, { detail: 'mock route not found', code: 'NOT_FOUND' })
  }
  const [, , pattern, handler, access] = route

  const claims = decodeJwt(init.headers?.Authorization?.replace(/^Bearer /, ''))
  let result
  if (access !== 'none' && (!claims || isExpired(claims))) {
    result = service === 'auth' ? javaError(401, 'UNAUTHORIZED', 'login required') : aiError(401, 'UNAUTHORIZED', 'login required')
  } else if ((access === 'team' || access === 'admin') && claims.team_id == null) {
    result = aiError(403, 'NO_TEAM', 'no team')
  } else if (access === 'admin' && claims.role !== 'team_admin') {
    result = aiError(403, 'FORBIDDEN', 'admin only')
  } else {
    result = handler({
      body: typeof init.body === 'string' ? JSON.parse(init.body) : null,
      formData: init.body instanceof FormData ? init.body : null,
      query: url.searchParams,
      params: pattern.exec(url.pathname).groups ?? {},
      claims,
    })
  }
  const [status, payload, delay] = result
  await wait(delay ?? between(500, 1200), init.signal)
  return respond(status, payload)
}
