// 실행: npm test (node --test)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import * as levels from './levels.js'
import { canReask, depthNote, REASK_LEVEL, reaskLevel } from './levels.js'

test('수준·관점·팀 유형 선택 API는 더 이상 없다: 남은 것은 더 쉽게/더 깊게뿐', () => {
  assert.deepEqual(Object.keys(levels).sort(), ['REASK_LEVEL', 'canReask', 'depthNote', 'reaskLevel'])
  assert.deepEqual(REASK_LEVEL, { easier: 'L1', deeper: 'L3' })
})

test('reaskLevel: 쉬움(L1) ← 기본 → 깊음(L3) 사다리', () => {
  // 기본에서 한 칸
  assert.equal(reaskLevel(undefined, 'easier'), 'L1')
  assert.equal(reaskLevel(null, 'deeper'), 'L3')
  // 반대쪽에서는 기본으로 돌아온다 (level을 보내지 않는다)
  assert.equal(reaskLevel('L3', 'easier'), null)
  assert.equal(reaskLevel('L1', 'deeper'), null)
  // 이미 끝이면 그대로
  assert.equal(reaskLevel('L1', 'easier'), 'L1')
  assert.equal(reaskLevel('L3', 'deeper'), 'L3')
})

test('canReask: 같은 방향 끝에서만 비활성', () => {
  assert.equal(canReask(undefined, 'easier'), true)
  assert.equal(canReask(undefined, 'deeper'), true)
  assert.equal(canReask('L1', 'easier'), false)
  assert.equal(canReask('L1', 'deeper'), true)
  assert.equal(canReask('L3', 'deeper'), false)
  assert.equal(canReask('L3', 'easier'), true)
})

test('depthNote: 기본 깊이는 표시하지 않는다', () => {
  assert.equal(depthNote('L1'), '쉬운 설명')
  assert.equal(depthNote('L3'), '깊은 설명')
  assert.equal(depthNote(null), '')
  assert.equal(depthNote(undefined), '')
  assert.equal(depthNote('L2'), '')
})
