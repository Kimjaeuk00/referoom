// VITE_USE_MOCK=true일 때만 불러온다. 서버 대신 같은 모양의 응답을 0.5~3초 지연 후 돌려준다(DEV_02 6절).
// 응답 모양은 DEV_01(인증)·DEV_03(라이브러리)·DEV_04(질의·음성)의 예시 JSON을 따른다.
// 데모 흐름은 DEV_05 5.1과 같다: LoRA·QLoRA는 이미 라이브러리에 있고, DoRA는 Zotero 동기화로, VeRA는 주제 수집으로 들어온다.
// 상태는 메모리에만 있어서 새로고침하면 처음으로 돌아간다.
//
// 계정(비밀번호는 아무 값): minsu(개발팀 팀원) · admin(개발팀 관리자) · rnd(R&D팀 관리자, 빈 라이브러리) · noteam(팀 없음) · fail(실패)
// 초대 코드: K3F9Q2XA(플랫폼개발팀), R7M2PQ4C(선행연구팀)
// 질문으로 시나리오 고르기(/rag-query):
//   기본 → LoRA 답변(출처 2개) / "어텐션"·"수식" → needs_review / "DoRA"·"VeRA"(라이브러리에 없을 때)·"없는" → handoff
//   "503" → NOT_READY / "타임아웃" → UPSTREAM_TIMEOUT / "401" → TOKEN_EXPIRED / "느린" → 12초 지연 / "xss" → sanitize 확인
// 새 모드(선행연구·주제·검증, PRD v0.2 8절): 입력·힌트·원고 어디에 써도 같은 키워드가 통한다.
//   선행연구(/rag-query mode=prior): 정리표(table) 포함 / 주제(/topic-suggest): 후보 4개, 대상 논문 1~10편 / 검증(/verify): 판정 5종
//   "없는" → handoff / "503"·"타임아웃"·"401"·"느린"·"xss"는 위와 같다 / 검증에 "DoRA"를 쓰면 모든 주장이 근거 없음(handoff)
//   주제는 QLoRA만 고르면 한계 서술이 없어 handoff(PRD: 한계 근거 0건)
// 수집은 후보를 직접 고른 1~10편만(자동 선택 없음). 수집 되돌리기와 Zotero 설정 저장·해제는 서버에 없다.
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

addUser({ username: 'minsu', displayName: '민수', teamId: 3 })
addUser({ username: 'admin', displayName: '지원', role: 'team_admin', teamId: 3 })
addUser({ username: 'rnd', displayName: '서준', role: 'team_admin', teamId: 4 })
addUser({ username: 'noteam', displayName: '서연' })

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
  const { username, password, displayName, teamMode, teamName, teamType, teamCode } = body ?? {}
  if (!username || username.length < 4 || username.length > 50 || !password || password.length < 8)
    return javaError(422, 'VALIDATION_ERROR', 'invalid input')
  if (users.has(username)) return javaError(409, 'CONFLICT', 'username exists')
  if (teamMode === 'join') {
    const team = teamByCode(teamCode)
    if (!team) return javaError(404, 'TEAM_NOT_FOUND', 'team not found')
    addUser({ username, displayName, teamId: team.id })
    return [201, { ok: true, teamId: team.id, role: 'member' }]
  }
  if (teamMode === 'create') {
    const id = Math.max(...TEAMS.keys()) + 1
    const inviteCode = Math.random().toString(36).slice(2, 10).toUpperCase().padEnd(8, 'X')
    TEAMS.set(id, { id, name: teamName, type: teamType, inviteCode })
    addUser({ username, displayName, role: 'team_admin', teamId: id })
    return [201, { ok: true, teamId: id, role: 'team_admin', inviteCode }]
  }
  addUser({ username, displayName })
  return [201, { ok: true, teamId: null, role: 'member' }]
}

function me({ claims }) {
  const user = userOf(claims)
  return user ? [200, { user: publicUser(user) }] : javaError(401, 'UNAUTHORIZED', 'unknown user')
}

function updateProfile({ body, claims }) {
  const user = userOf(claims)
  if (!user) return javaError(401, 'UNAUTHORIZED', 'unknown user')
  if (body?.level == null && body?.view == null) return javaError(400, 'VALIDATION_ERROR', 'level 또는 view가 필요합니다')
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
    removed: 0,
    error_msg: null,
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
  return [202, { batch_id: batch.id, paper_id: null, status: 'pending' }] // 서버는 Zotero 항목을 만든 뒤에야 paper_id가 정해진다
}

const CANDIDATES = [
  { candidate_id: '2310.11454', title: 'VeRA: Vector-based Random Matrix Adaptation', authors: ['Dawid J. Kopiczko', 'Tijmen Blankevoort', 'Yuki M. Asano'], year: 2023, abstract: '층마다 공유하는 무작위 행렬은 고정하고, 작은 스케일 벡터만 학습해 LoRA보다 학습 파라미터를 더 줄이는 방법.', relevance: 0.91 },
  { candidate_id: '2402.12354', title: 'LoRA+: Efficient Low Rank Adaptation of Large Models', authors: ['Soufiane Hayou', 'Nikhil Ghosh', 'Bin Yu'], year: 2024, abstract: 'LoRA의 두 행렬 A와 B에 서로 다른 학습률을 주면 학습이 더 빨라진다는 분석.', relevance: 0.78 },
  { candidate_id: '2106.09685', title: 'LoRA: Low-Rank Adaptation of Large Language Models', authors: ['Edward J. Hu', 'Yelong Shen'], year: 2021, abstract: '사전학습 가중치는 고정하고 저랭크 분해 행렬만 학습하는 미세조정 방법.', relevance: 0.74 },
  { candidate_id: '2303.10512', title: 'AdaLoRA: Adaptive Budget Allocation for Parameter-Efficient Fine-Tuning', authors: ['Qingru Zhang', 'Minshuo Chen'], year: 2023, abstract: '층마다 중요도에 따라 LoRA 랭크를 다르게 배분하는 방법.', relevance: 0.69 },
  { candidate_id: '2309.14717', title: 'QA-LoRA: Quantization-Aware Low-Rank Adaptation of Large Language Models', authors: ['Yuhui Xu', 'Lingxi Xie'], year: 2023, abstract: '양자화된 모델의 정밀도를 유지한 채 LoRA 어댑터를 합칠 수 있게 하는 방법.', relevance: 0.66 },
  { candidate_id: '2309.12307', title: 'LongLoRA: Efficient Fine-tuning of Long-Context Large Language Models', authors: ['Yukang Chen', 'Shengju Qian'], year: 2023, abstract: '긴 문맥으로 확장할 때 어텐션 비용을 줄이는 미세조정 방법.', relevance: 0.63 },
  { candidate_id: '2404.02948', title: 'PiSSA: Principal Singular Values and Singular Vectors Adaptation', authors: ['Fanxu Meng', 'Zhaohui Wang'], year: 2024, abstract: '가중치의 주요 특이값 성분으로 어댑터를 초기화해 수렴을 빠르게 하는 방법.', relevance: 0.61 },
  { candidate_id: '2403.03507', title: 'GaLore: Memory-Efficient LLM Training by Gradient Low-Rank Projection', authors: ['Jiawei Zhao', 'Zhenyu Zhang'], year: 2024, abstract: '그래디언트를 저랭크로 투영해 전체 파라미터 학습의 메모리를 줄이는 방법.', relevance: 0.58 },
  { candidate_id: '2405.09673', title: 'LoRA Learns Less and Forgets Less', authors: ['Dan Biderman', 'Jacob Portes'], year: 2024, abstract: 'LoRA와 전체 미세조정이 새로 배우는 양과 잊는 양을 비교한 실험 분석.', relevance: 0.55 },
  { candidate_id: '2311.03285', title: 'S-LoRA: Serving Thousands of Concurrent LoRA Adapters', authors: ['Ying Sheng', 'Shiyi Cao'], year: 2023, abstract: '수많은 LoRA 어댑터를 한 서버에서 동시에 서빙하는 시스템.', relevance: 0.52 },
  { candidate_id: '2001.08361', title: 'Scaling Laws for Neural Language Models', authors: ['Jared Kaplan', 'Sam McCandlish'], year: 2020, abstract: '모델 크기, 데이터, 연산량에 따른 언어 모델 손실의 거듭제곱 법칙.', relevance: 0.31 },
]
const MIN_RELEVANCE = 0.5 // 서버의 TOPIC_MIN_RELEVANCE 기본값(실제 arXiv 후보 40건으로 보정)

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
  return [200, { topic, candidates: candidatesFor(claims).sort((a, b) => b.relevance - a.relevance).slice(0, body.max_results ?? 10) }]
}

function uploadTopic({ body, claims }) {
  const topic = String(body?.topic ?? '').trim()
  const pool = candidatesFor(claims).filter((c) => !c.already_in_library)
  // 사용자가 고른 논문만 수집한다(자동 선택 없음). 한 번에 1~10편, 이미 있는 논문은 뺀다.
  if (!Array.isArray(body?.selected) || body.selected.length < 1 || body.selected.length > 10) return aiError(422, 'VALIDATION_ERROR', '1~10편을 고르세요.')
  const picked = pool.filter((c) => body.selected.includes(c.candidate_id))
  if (picked.length === 0) return aiError(422, 'VALIDATION_ERROR', '선택한 논문이 이미 모두 라이브러리에 있습니다.')
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

  const level = body.level ?? 'L2' // 요청의 level(더 쉽게/더 깊게)만 쓰고 JWT claim은 무시한다(v0.2)
  const view = body.view ?? claims.view ?? 'dev'
  const delay = question.includes('느린') ? 12_000 : between(1500, 3000)
  const meta = { view, latency_ms: delay }
  const handoff = [200, { ...meta, answer: '팀 라이브러리에서 관련 내용을 찾을 수 없습니다.', sources: [], source_details: [], needs_review: false, handoff: true }, delay]

  if (teamPapers(claims).every((p) => p.status !== 'indexed') || /없는/.test(question)) return handoff
  if (body.mode === 'prior') return priorQuery({ body, claims, meta, handoff, delay })
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

// ---------- 선행연구·주제·검증 (PRD v0.2 8절, 서버 구현 전이라 mock으로 먼저 만든다) ----------
function scenarioError(text) {
  if (text.includes('503')) return aiError(503, 'NOT_READY', '인덱스 준비 중')
  if (text.includes('타임아웃')) return aiError(503, 'UPSTREAM_TIMEOUT', 'LLM timeout')
  if (text.includes('401')) return aiError(401, 'TOKEN_EXPIRED', '토큰 만료')
  return null
}
const modeDelay = (text, min, max) => (text.includes('느린') ? 12_000 : between(min, max))
// ids가 배열이면 그 논문 중 색인된 것만, 아니면 팀의 색인된 논문 전체
const indexedPapers = (claims, ids) => (Array.isArray(ids) ? ids.map((id) => findPaper(claims, id)) : teamPapers(claims)).filter((p) => p?.status === 'indexed')

// 논문별로 정리표 칸을 채울 내용 (arXiv ID로 찾는다). null인 칸은 화면에서 '논문에 명시되지 않음'으로 보인다.
const PRIOR_FACTS = {
  '2106.09685': { problem: '대형 모델 전체 미세조정의 학습·저장 비용', method: '사전학습 가중치를 고정하고 저랭크 행렬 B, A만 학습', dataset: 'GLUE, E2E NLG, WikiSQL', metric: 'GLUE 평균, BLEU', result: 'GPT-3 175B에서 학습 파라미터를 약 10,000분의 1로 줄이고도 전체 미세조정과 비슷한 성능', limitation: '어느 층에 붙일지와 랭크 r을 실험으로 정해야 한다', page: 4 },
  '2305.14314': { problem: '65B 모델 미세조정에 필요한 GPU 메모리', method: '4비트 NormalFloat 양자화에 LoRA를 더하고 이중 양자화·페이징 옵티마이저 사용', dataset: 'MMLU, Vicuna 벤치마크', metric: '정확도, Elo', result: '65B 모델을 48GB GPU 한 장에서 학습하면서 16비트 미세조정 성능 유지', limitation: null, page: 3 },
  '1706.03762': { problem: '순환 구조 없이 긴 문장을 병렬로 처리', method: '셀프 어텐션만으로 인코더·디코더를 구성', dataset: 'WMT 2014 영-독, 영-불', metric: 'BLEU', result: '영-독 28.4 BLEU로 당시 최고 성능, 학습 비용은 더 낮음', limitation: '어텐션 비용이 시퀀스 길이의 제곱에 비례한다', page: 6 },
  '2005.11401': { problem: '지식 집약 과제에서 모델 파라미터만으로는 최신·정확한 지식이 부족', method: '검색기로 찾은 문서를 생성기에 함께 넣는 RAG', dataset: 'Natural Questions, TriviaQA', metric: 'Exact Match', result: '개방형 질의응답에서 파라미터만 쓰는 모델보다 높은 성능', limitation: null, page: 5 },
  '2310.11454': { problem: 'LoRA보다 학습 파라미터를 더 줄이고 싶다', method: '모든 층이 공유하는 무작위 행렬은 고정하고 층별 스케일 벡터만 학습', dataset: 'GLUE, E2E', metric: 'GLUE 평균', result: 'LoRA 대비 학습 파라미터를 10배 이상 줄이고 비슷한 성능', limitation: '큰 모델에서의 검증이 제한적이다', page: 2 },
  '2402.09353': { problem: 'LoRA와 전체 미세조정 사이의 성능 격차', method: '가중치를 크기와 방향으로 나누고 방향에만 LoRA 적용', dataset: 'Commonsense reasoning 8종', metric: '정확도', result: 'LoRA보다 평균 정확도가 높고 추론 비용은 같다', limitation: '크기 성분 학습이 추가 메모리를 쓴다', page: 3 },
}
const GENERIC_FACTS = { problem: '논문이 풀려는 문제 요약(목업)', method: '핵심 방법 요약(목업)', dataset: null, metric: null, result: '주요 결과 요약(목업)', limitation: null, page: 2 }
const factsOf = (paper) => PRIOR_FACTS[paper.arxiv_id] ?? GENERIC_FACTS
const shortTitle = (paper) => paper.title.split(':')[0]

function priorQuery({ body, claims, meta, handoff, delay }) {
  const ids = body.scope?.type === 'paper' ? body.scope.ids : null
  const targets = Array.isArray(ids) ? indexedPapers(claims, ids).slice(0, 10) : indexedPapers(claims).slice(0, 3)
  if (!targets.length) return handoff
  const details = []
  let n = 0
  const rows = targets.map((paper) => {
    const facts = factsOf(paper)
    const labels = {}
    for (const key of ['method', 'result', 'limitation']) {
      if (!facts[key]) continue
      labels[key] = `S${++n}`
      details.push(detail(paper.id, labels[key], facts.page, facts[key]))
    }
    return { paper_id: paper.id, title: paper.title, problem: facts.problem, method: facts.method, dataset: facts.dataset, metric: facts.metric, result: facts.result, limitation: facts.limitation, labels }
  })
  const list = rows.map((r) => `- **${shortTitle(r)}**: ${r.method}${r.labels.method ? ` [${r.labels.method}]` : ''}`).join('\n')
  const answer = `선택한 ${rows.length}편을 방법과 주요 결과 기준으로 정리했어요.\n\n${list}\n\n칸마다 근거가 된 쪽수를 달았어요. 자세한 비교는 아래 정리표를 보세요.`
  const needsReview = rows.some((r) => /\d/.test(r.result ?? ''))
  return [200, { ...meta, answer, sources: sourcesOf(details), source_details: details, needs_review: needsReview, handoff: false, table: rows }, delay]
}

function topicSuggest({ body, claims }) {
  const ids = body?.paper_ids
  if (!Array.isArray(ids) || ids.length < 1 || ids.length > 10 || !ids.every(Number.isInteger)) return aiError(422, 'VALIDATION_ERROR', '대상 논문은 1~10편이어야 합니다.')
  const hint = String(body.hint ?? '')
  const failed = scenarioError(hint)
  if (failed) return failed
  const view = body.view ?? claims.view ?? 'dev'
  const delay = modeDelay(hint, 3000, 4500)
  const handoff = [200, { limitations: [], topics: [], sources: [], source_details: [], needs_review: false, handoff: true, view, latency_ms: delay }, delay]
  const targets = indexedPapers(claims, ids).filter((p) => factsOf(p).limitation) // 한계 서술이 있는 논문만 근거가 된다
  if (!targets.length || /없는/.test(hint)) return handoff

  const details = []
  const limitations = targets.map((paper, i) => {
    const facts = factsOf(paper)
    const label = `S${i + 1}`
    details.push(detail(paper.id, label, facts.page + 4, facts.limitation))
    return { label, paper_id: paper.id, title: paper.title, page: facts.page + 4, summary: facts.limitation }
  })
  const pick = (...indexes) => [...new Set(indexes.map((i) => limitations[i % limitations.length].label))]
  const other = indexedPapers(claims).find((p) => !ids.includes(p.id))
  const evil = /xss/i.test(hint)
  const templates = [
    { perspective: 'limitation_fix', title: evil ? '<script>alert("xss")</script> 층별 중요도에 따른 동적 랭크 할당' : '층별 중요도에 따른 동적 랭크 할당', question: evil ? '<img src=x onerror="alert(1)"> 랭크를 고정하지 않고 층마다 다르게 두면 어떻게 되는가?' : '랭크를 고정하지 않고 층마다 다르게 배분하면 같은 파라미터 예산에서 성능이 오르는가?', approach: '학습 중 층별 기여도를 측정해 랭크를 늘리거나 줄인다.', experiment: { datasets: ['GLUE', 'E2E NLG'], baselines: ['LoRA', '고정 랭크 r=8'], metrics: ['평균 점수', '학습 파라미터 수'] }, based_on: pick(0), similar: other },
    { perspective: 'combine', title: '양자화와 구조화된 어댑터의 결합', question: '서로 다른 두 방법의 장점을 합치면 각각의 한계를 함께 줄일 수 있는가?', approach: '한쪽 논문의 메모리 절감 기법을 다른 쪽 논문의 적응 구조에 적용한다.', experiment: { datasets: ['MMLU'], baselines: ['각 방법 단독'], metrics: ['정확도', 'GPU 메모리'] }, based_on: pick(0, 1) },
    { perspective: 'extend', title: '다국어·저자원 도메인으로의 일반화 검증', question: '영어 벤치마크에서 확인된 성능이 다른 언어와 도메인에서도 유지되는가?', approach: '한국어·의료 문서 같은 저자원 도메인에 같은 설정을 적용해 성능 하락 원인을 분석한다.', experiment: { datasets: ['KLUE', '의료 QA'], baselines: ['전체 미세조정'], metrics: ['정확도', 'F1'] }, based_on: pick(1) },
    { perspective: 'efficiency', title: '추론 지연 없이 학습 비용을 더 줄이는 방법', question: '학습 단계의 메모리와 시간을 줄이면서도 배포 시 지연이 늘지 않게 할 수 있는가?', approach: '학습 중에만 쓰는 보조 구조를 두고 배포 전에 원래 가중치에 합친다.', experiment: { datasets: ['GLUE'], baselines: ['LoRA'], metrics: ['학습 시간', '피크 메모리', '추론 지연'] }, based_on: pick(0, 1) },
  ]
  const topics = templates.slice(0, Math.min(Math.max(Number(body.n) || 4, 1), 4)).map(({ similar, ...t }) => ({
    ...t,
    similar_papers: similar && t.perspective === 'limitation_fix' ? [{ paper_id: similar.id, title: similar.title, score: 0.71 }] : [],
    ai_generated: true,
  }))
  return [200, { limitations, topics, sources: sourcesOf(details), source_details: details, needs_review: true, handoff: false, view, latency_ms: delay }, delay]
}

const claim = (fields) => ({ sentence: '', subject: null, metric: null, claimed_value: null, dataset: null, found_value: null, condition: null, verdict: 'not_found', labels: [], delta: null, ...fields })

function verifyManuscript({ body, claims }) {
  const text = String(body?.text ?? '').trim()
  if (text.length < 10 || text.length > 3000) return aiError(422, 'VALIDATION_ERROR', '원고는 10~3000자여야 합니다.')
  if (body.paper_ids != null && !(Array.isArray(body.paper_ids) && body.paper_ids.every(Number.isInteger))) return aiError(422, 'VALIDATION_ERROR', '대상 논문 형식이 올바르지 않습니다.')
  const failed = scenarioError(text)
  if (failed) return failed
  const view = body.view ?? claims.view ?? 'dev'
  const delay = modeDelay(text, 3500, 5000)
  const base = { sources: [], source_details: [], needs_review: true, view, latency_ms: delay } // 수치를 다루므로 항상 검토 필요(PRD 5.4)
  const scoped = indexedPapers(claims, body.paper_ids ?? undefined)

  if (/dora|없는/i.test(text) || !scoped.length) {
    const notFound = [
      claim({ sentence: 'DoRA는 MMLU에서 71.2를 기록한다', subject: 'DoRA', metric: 'MMLU avg', claimed_value: '71.2', dataset: 'MMLU' }),
      claim({ sentence: 'DoRA는 LoRA보다 1.4p 높다', subject: 'DoRA', metric: 'MMLU avg', claimed_value: '+1.4p', dataset: 'MMLU' }),
    ]
    return [200, { ...base, claims: notFound, draft: '', warnings: ['라이브러리에서 비교할 값을 찾지 못했어요. 선행연구 모드로 해당 논문을 먼저 모아 주세요.'], handoff: true }, delay]
  }

  const lora = findPaper(claims, 41)?.status === 'indexed' ? 41 : scoped[0].id
  const qlora = findPaper(claims, 42)?.status === 'indexed' ? 42 : scoped[0].id
  const details = [
    detail(lora, 'S1', 5, 'RoBERTa-base에서 LoRA의 학습 파라미터는 0.3M이다.'),
    detail(lora, 'S2', 7, 'RoBERTa-base GLUE 평균: LoRA 87.2.'),
    detail(qlora, 'S3', 2, '65B 모델을 48GB GPU 한 장에서 미세조정할 수 있다.'),
  ]
  const evil = /xss/i.test(text)
  const result = [
    claim({ sentence: 'LoRA는 학습 파라미터가 0.3M이다', subject: 'LoRA', metric: 'trainable params', claimed_value: '0.3M', dataset: 'RoBERTa-base', found_value: '0.3M', condition: 'RoBERTa-base 기준', verdict: 'match', labels: ['S1'] }),
    claim({ sentence: 'LoRA(87.2)', subject: 'LoRA', metric: 'GLUE avg', claimed_value: '87.2', dataset: 'GLUE', found_value: '87.2', condition: 'RoBERTa-base 기준이에요. 원고에 모델 크기가 없어요.', verdict: 'condition_differs', labels: ['S2'] }),
    claim({ sentence: 'QLoRA는 65B를 24GB GPU 한 장에서 학습한다', subject: 'QLoRA', metric: '필요 GPU 메모리', claimed_value: '24GB', dataset: null, found_value: '48GB', condition: null, verdict: 'mismatch', labels: ['S3'] }),
    claim({ sentence: '우리 방법은 GLUE 평균 88.1이다', subject: '제안 방법', metric: 'GLUE avg', claimed_value: '88.1', dataset: 'GLUE', verdict: 'own_result', delta: { vs: 'LoRA', value: 0.9 } }),
  ]
  const draft = evil
    ? '<script>alert("xss")</script> 제안 방법은 GLUE 평균 88.1을 기록해 LoRA의 87.2 [S2] 대비 0.9p 높다. <img src=x onerror="alert(1)">'
    : '제안 방법은 GLUE 평균 88.1을 기록해 LoRA의 87.2 [S2] 대비 0.9p 높다. 다만 비교 대상의 모델 크기가 원고에 명시되지 않아 직접 비교에는 주의가 필요하다 [S2]. QLoRA는 65B 모델을 48GB GPU 한 장에서 학습할 수 있다 [S3].'
  const warnings = evil ? ['<b onmouseover="alert(1)">경고</b>'] : ['비교 대상 모델 크기가 원고에 명시되지 않았어요.']
  return [200, { ...base, claims: result, draft, warnings, sources: sourcesOf(details), source_details: details, handoff: false }, delay]
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
  return [200, { paper_id: paper.id, title: paper.title, view, sections, needs_review: true, latency_ms: 9100 }, between(2000, 3000)]
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
  const [status, rag] = ragQuery({ body: { question: 'LoRA는 어떤 파라미터를 학습해?', view: formData.get('view') }, claims })
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
  ['DELETE', 'rag', /^\/papers\/(?<id>[^/]+)$/, deletePaper, 'team'],
  ['POST', 'rag', /^\/upload-paper$/, uploadPaper, 'team'],
  ['POST', 'rag', /^\/search-topic$/, searchTopic, 'team'],
  ['POST', 'rag', /^\/upload-topic$/, uploadTopic, 'team'],
  ['GET', 'rag', /^\/ingest\/batches\/(?<id>[^/]+)$/, getBatch, 'team'],
  ['GET', 'rag', /^\/zotero\/config$/, getZoteroConfig, 'admin'],
  ['POST', 'rag', /^\/zotero\/sync$/, syncZotero, 'admin'],
  ['POST', 'rag', /^\/rag-query$/, ragQuery, 'team'],
  ['POST', 'rag', /^\/summary$/, summary, 'team'],
  ['POST', 'rag', /^\/topic-suggest$/, topicSuggest, 'team'],
  ['POST', 'rag', /^\/verify$/, verifyManuscript, 'team'],
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
