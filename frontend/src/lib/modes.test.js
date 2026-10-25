// 실행: npm test (node --test)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  CHIP_MODES, collectedPaperIds, csvCell, EMPTY_CELL, MAX_COLLECT, MODE_ORDER, MODES, PERSPECTIVES, perspectiveOf, PRIOR_COLUMNS,
  priorTableToCsv, priorTableToMarkdown, buildRequest, validateInput, VERDICTS, verdictOf, manuscriptPreview, formatDelta,
} from './modes.js'

const has = (object, key) => Object.hasOwn(object, key)

test('MODES: 이름·입력 한도·경로', () => {
  assert.deepEqual(MODE_ORDER, ['tutor', 'prior', 'topic', 'verify'])
  assert.deepEqual(CHIP_MODES, ['prior', 'topic', 'verify'])
  assert.deepEqual(MODE_ORDER.map((m) => MODES[m].label), ['튜터', '선행연구', '주제', '검증'])
  assert.equal(MODES.verify.max, 3000)
  assert.ok(['tutor', 'prior', 'topic'].every((m) => MODES[m].max === 1000))
  assert.deepEqual(MODE_ORDER.map((m) => MODES[m].path), ['/rag-query', '/rag-query', '/topic-suggest', '/verify'])
  assert.equal(MAX_COLLECT, 10)
})

test('buildRequest: level은 값을 줄 때(더 쉽게/더 깊게)만 body에 들어간다', () => {
  for (const mode of ['tutor', 'prior']) {
    const plain = buildRequest(mode, { question: ' LoRA란? ', view: 'rnd' })
    assert.equal(plain.path, '/rag-query')
    assert.equal(has(plain.body, 'level'), false, `${mode}: level이 없어야 한다`)
    assert.deepEqual(plain.body, { question: 'LoRA란?', mode, source: 'all', scope: undefined, view: 'rnd', top_k: 5 })
    assert.equal(buildRequest(mode, { question: '질문', view: 'dev', level: 'L1' }).body.level, 'L1')
  }
  for (const mode of ['topic', 'verify']) assert.equal(has(buildRequest(mode, { question: '원고 '.repeat(5), paperIds: [1], view: 'dev', level: 'L3' }).body, 'level'), false)
})

test('buildRequest: 선행연구는 수집한 논문이 있으면 그것으로 범위를 정한다', () => {
  const scope = { type: 'tag', tags: ['peft'] }
  assert.deepEqual(buildRequest('prior', { question: '비교', view: 'rnd', scope }).body.scope, scope)
  const body = buildRequest('prior', { question: '비교', view: 'rnd', scope, priorIds: ['41', 42] }).body
  assert.deepEqual(body.scope, { type: 'paper', ids: [41, 42] })
  assert.equal(body.mode, 'prior')
  assert.equal(buildRequest('tutor', { question: '질문', view: 'dev', scope, priorIds: [1] }).body.scope, scope) // 튜터는 priorIds를 쓰지 않는다
})

test('buildRequest: 주제·검증 요청 형식', () => {
  const topic = buildRequest('topic', { question: '  메모리 효율  ', paperIds: ['41', 42], view: 'rnd' })
  assert.deepEqual(topic, { path: '/topic-suggest', timeoutKey: 'long', body: { paper_ids: [41, 42], hint: '메모리 효율', n: 4, view: 'rnd' } })
  assert.equal(buildRequest('topic', { question: '', paperIds: [1], view: 'dev' }).body.hint, '')
  const verify = buildRequest('verify', { question: '우리 방법은 GLUE 평균 88.1이다', view: 'rnd' })
  assert.deepEqual(verify, { path: '/verify', timeoutKey: 'long', body: { text: '우리 방법은 GLUE 평균 88.1이다', paper_ids: null, view: 'rnd' } })
  assert.deepEqual(buildRequest('verify', { question: '원고 '.repeat(5), paperIds: [3, '4'], view: 'dev' }).body.paper_ids, [3, 4])
  assert.throws(() => buildRequest('nope', {}), /알 수 없는 모드/)
})

test('validateInput: 모드별 입력 규칙', () => {
  assert.equal(validateInput('tutor', 'LoRA란?'), null)
  assert.match(validateInput('tutor', ' a '), /2자/)
  assert.match(validateInput('prior', 'x'), /2자/)
  assert.equal(validateInput('prior', 'a'.repeat(1000)), null)
  assert.match(validateInput('prior', 'a'.repeat(1001)), /1,000자/)
  // 주제: 대상 논문 1~10편 필수, 힌트는 비워도 된다
  assert.equal(validateInput('topic', '', [1]), null)
  assert.equal(validateInput('topic', '', Array.from({ length: MAX_COLLECT }, (_, i) => i + 1)), null)
  assert.equal(validateInput('topic', '', []), '대상 논문을 선택하세요.')
  assert.match(validateInput('topic', '', Array.from({ length: MAX_COLLECT + 1 }, (_, i) => i + 1)), /10편까지/)
  assert.match(validateInput('topic', 'a'.repeat(1001), [1]), /1,000자/)
  // 검증: 10자 이상 3000자 이하, 논문 선택은 선택
  assert.match(validateInput('verify', 'a'.repeat(9)), /10자 이상/)
  assert.equal(validateInput('verify', 'a'.repeat(10)), null)
  assert.equal(validateInput('verify', 'a'.repeat(3000)), null)
  assert.match(validateInput('verify', 'a'.repeat(3001)), /3,000자/)
  assert.equal(validateInput('verify', `  ${'a'.repeat(10)}  `), null) // 앞뒤 공백은 세지 않는다
  assert.match(validateInput('nope', 'abc'), /알 수 없는/)
})

test('VERDICTS: 판정 5종은 이름·아이콘·색 계열이 모두 달라 색만으로 구분하지 않는다', () => {
  assert.deepEqual(Object.keys(VERDICTS), ['match', 'mismatch', 'condition_differs', 'not_found', 'own_result'])
  assert.deepEqual(Object.values(VERDICTS).map((v) => v.label), ['일치', '불일치', '조건 다름', '근거 없음', '본인 결과'])
  assert.equal(new Set(Object.values(VERDICTS).map((v) => v.icon)).size, 5)
  assert.ok(Object.values(VERDICTS).every((v) => v.tone && v.desc))
  assert.equal(verdictOf('match').label, '일치')
  assert.equal(verdictOf('weird').label, 'weird') // 모르는 판정도 깨지지 않는다
  assert.equal(verdictOf(undefined).icon, '·')
})

test('PERSPECTIVES: 주제 관점 5종', () => {
  assert.deepEqual(Object.values(PERSPECTIVES), ['한계 직접 해결', '방법 결합', '도메인·데이터 확장', '효율·자원', '평가·분석'])
  assert.equal(perspectiveOf('combine'), '방법 결합')
  assert.equal(perspectiveOf('new'), 'new')
})

test('csvCell: 수식 주입을 막고 쉼표·따옴표·줄바꿈을 감싼다', () => {
  for (const evil of ['=1+1', '+SUM(A1)', '-5', '@cmd', '\tTAB', '\rCR']) assert.ok(csvCell(evil).replace(/^"/, '').startsWith("'"), `${JSON.stringify(evil)} → ${csvCell(evil)}`)
  assert.equal(csvCell('LoRA'), 'LoRA')
  assert.equal(csvCell('a,b'), '"a,b"')
  assert.equal(csvCell('say "hi"'), '"say ""hi"""')
  assert.equal(csvCell('line1\nline2'), '"line1\nline2"')
  assert.equal(csvCell('=A1,B1'), '"\'=A1,B1"') // 수식 방지와 따옴표 감싸기가 함께 적용된다
  assert.equal(csvCell(null), '')
  assert.equal(csvCell(87.2), '87.2')
  assert.equal(csvCell('3-5'), '3-5') // 가운데 있는 -는 건드리지 않는다
})

const ROWS = [
  { paper_id: 41, title: 'LoRA: Low-Rank Adaptation', problem: '전체 미세조정 비용', method: '저랭크 행렬 BA만 학습', dataset: 'GLUE | E2E', metric: null, result: '', limitation: '=랭크 선택 필요', labels: { method: 'S1', result: 'S2', limitation: 'S3' } },
  { paper_id: 42, title: 'QLoRA', problem: '메모리', method: '4bit 양자화\n+ LoRA', dataset: 'MMLU', metric: 'accuracy', result: '48GB 한 장', limitation: null, labels: { method: 'S4' } },
]

test('priorTableToMarkdown: 머리글·빈 칸·인용·이스케이프', () => {
  const lines = priorTableToMarkdown(ROWS).split('\n')
  assert.equal(lines.length, 4)
  assert.equal(lines[0], `| 논문 | ${PRIOR_COLUMNS.map(([, name]) => name).join(' | ')} |`)
  assert.equal(lines[1], '| --- | --- | --- | --- | --- | --- | --- |')
  assert.ok(lines[2].includes('저랭크 행렬 BA만 학습 [S1]'))
  assert.ok(lines[2].includes('GLUE \\| E2E'), '칸 안의 |는 이스케이프')
  assert.ok(lines[2].includes(`| ${EMPTY_CELL} | ${EMPTY_CELL} |`), 'metric(null)과 result(빈 문자열)는 같은 문구')
  assert.ok(!lines[2].includes('[S2]'), '값이 없는 칸에는 인용을 붙이지 않는다')
  assert.ok(lines[3].includes('4bit 양자화 + LoRA [S4]'), '줄바꿈은 공백으로')
  assert.equal(priorTableToMarkdown([]).split('\n').length, 2) // 행이 없어도 머리글은 나온다
})

test('priorTableToCsv: 수식 주입 방지, CRLF, BOM 옵션', () => {
  const csv = priorTableToCsv(ROWS)
  const lines = csv.split('\r\n')
  assert.equal(lines.length, 3)
  assert.equal(lines[0], '논문,문제,방법,데이터셋,지표,주요 결과,한계')
  assert.ok(lines[1].includes("'=랭크 선택 필요 [S3]"), '=로 시작하는 칸은 작은따옴표를 붙인다')
  assert.ok(lines[1].includes('GLUE | E2E'))
  assert.ok(!csv.startsWith('﻿'))
  assert.ok(priorTableToCsv(ROWS, { bom: true }).startsWith('﻿논문'))
})

test('collectedPaperIds: 색인했거나 이미 있어 건너뛴 논문만, id 없는 항목·실패는 뺀다', () => {
  const batch = {
    papers: [
      { paper_id: 41, status: 'indexed' },
      { paper_id: 42, status: 'skipped' },
      { paper_id: 43, status: 'failed' },
      { paper_id: null, status: 'pending' },
      { paper_id: null, status: 'indexed' },
      { paper_id: 0, status: 'indexed' }, // 0도 id 값이므로 남긴다
    ],
  }
  assert.deepEqual(collectedPaperIds(batch), [41, 42, 0])
  assert.deepEqual(collectedPaperIds({ papers: [] }), [])
  assert.deepEqual(collectedPaperIds({}), [])
  assert.deepEqual(collectedPaperIds(null), [])
})

test('manuscriptPreview: 앞 80자와 글자 수만 남긴다', () => {
  const long = '원고 문장입니다. '.repeat(30)
  const preview = manuscriptPreview(long)
  assert.ok(preview.startsWith(long.replace(/\s+/g, ' ').trim().slice(0, 80)))
  assert.match(preview, /… \(원고 \d+자\)$/)
  assert.ok(!preview.includes(long.trim()), '전체 원고는 들어 있지 않다')
  assert.equal(manuscriptPreview(' 짧은   원고 '), '짧은 원고 (원고 5자)')
  assert.equal(manuscriptPreview(null), ' (원고 0자)')
})

test('formatDelta: 부호와 비교 대상', () => {
  assert.equal(formatDelta({ vs: 'LoRA', value: 0.9 }), '+0.9p (vs LoRA)')
  assert.equal(formatDelta({ value: -1.2 }), '-1.2p')
  assert.equal(formatDelta({ value: 0 }), '0p')
  assert.equal(formatDelta(null), '')
  assert.equal(formatDelta({ value: 'x' }), '')
})
