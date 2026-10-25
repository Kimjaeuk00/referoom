// 관점·팀 유형의 화면 이름과 설명 (기능명세서 2.2, 2.6), 그리고 '더 쉽게/더 깊게'가 그 요청 1회에만 보내는 level 값.
// v0.2: 설명 수준(L1~L3)은 사용자 설정이 아니다. 기본 깊이는 서버가 정하고, 이 두 버튼만 level을 실어 보낸다.
export const VIEWS = {
  dev: { name: '구현', desc: '적용 방법, 입출력, 하이퍼파라미터, 비용, 구현 주의점을 강조해요.' },
  rnd: { name: '연구', desc: '핵심 가정, 실험 설계, 기존 방법과 차이, 한계, 재현성을 강조해요.' },
}

export const TEAM_TYPES = {
  dev: { name: '개발팀', desc: '제품과 서비스를 만드는 팀이에요. 답변 관점의 기본값이 구현이에요.' },
  rnd: { name: 'R&D팀', desc: '연구와 선행 개발을 하는 팀이에요. 답변 관점의 기본값이 연구예요.' },
}

export const REASK_LEVEL = { easier: 'L1', deeper: 'L3' }

// 깊이는 세 단계다: 더 쉽게(L1) ← 기본(level 없음) → 더 깊게(L3). current는 지금 답변이 쓴 level(없으면 기본).
export const canReask = (current, direction) => current !== REASK_LEVEL[direction]

/** 같은 질문을 다시 물을 때 보낼 level. 기본 깊이로 돌아가면 null이고, 요청에는 level을 싣지 않는다. */
export function reaskLevel(current, direction) {
  const target = REASK_LEVEL[direction]
  if (current === target) return current
  const opposite = REASK_LEVEL[direction === 'easier' ? 'deeper' : 'easier']
  return current === opposite ? null : target
}

export const depthNote = (level) => (level === REASK_LEVEL.easier ? '쉬운 설명' : level === REASK_LEVEL.deeper ? '깊은 설명' : '')
