// 수준·관점·팀 유형의 화면 이름과 설명 (기능명세서 2.2, 2.6)
export const LEVELS = {
  L1: { name: '입문', desc: '비유와 직관 중심으로, 용어는 바로 풀어 주고 수식은 말로 설명해요.' },
  L2: { name: '실무', desc: '핵심 아이디어와 입출력, 하이퍼파라미터를 중심으로 설명해요.' },
  L3: { name: '심화', desc: '가정과 한계, 수식 유도, 재현할 때 주의할 점까지 다뤄요.' },
}

export const LEVEL_ORDER = ['L1', 'L2', 'L3']

export const VIEWS = {
  dev: { name: '구현', desc: '적용 방법, 입출력, 하이퍼파라미터, 비용, 구현 주의점을 강조해요.' },
  rnd: { name: '연구', desc: '핵심 가정, 실험 설계, 기존 방법과 차이, 한계, 재현성을 강조해요.' },
}

export const TEAM_TYPES = {
  dev: { name: '개발팀', desc: '제품과 서비스를 만드는 팀이에요. 답변 관점의 기본값이 구현이에요.' },
  rnd: { name: 'R&D팀', desc: '연구와 선행 개발을 하는 팀이에요. 답변 관점의 기본값이 연구예요.' },
}

export function levelLabel(level) {
  return LEVELS[level] ? `${level} ${LEVELS[level].name}` : level ?? ''
}
