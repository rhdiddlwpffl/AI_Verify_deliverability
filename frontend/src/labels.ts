import type { ClaimType } from './api/types'

export const CLAIM_TYPE_LABEL: Record<ClaimType, string> = {
  factual: '사실 주장',
  numeric: '수치 주장',
  quote: '인용',
  opinion: '의견',
  other: '기타',
}

// 취약점 신호의 화면 표시 이름. 모두 "다시 확인해 볼 점"이며 거짓이라는 뜻이 아니다.
const FLAG_LABEL: Record<string, string> = {
  absolute_expression: '단정적 표현',
  contains_number: '수치 포함',
  contains_year: '연도 포함',
  vague_attribution: '출처가 불명확한 인용',
  quotation: '따옴표 인용 (출처 없음)',
  overgeneralization: '과도한 일반화 가능성',
  unverifiable_specificity: '확인하기 어려운 세부 내용',
  causal_claim: '인과관계 단정',
  possibly_outdated: '시간이 지나 바뀌었을 수 있음',
}

export function claimTypeLabel(type: string): string {
  return CLAIM_TYPE_LABEL[type as ClaimType] ?? '기타'
}

export function flagLabel(flag: string): string {
  // 서버에 새 신호가 추가돼도 화면이 깨지지 않도록 모르는 값은 그대로 보여 준다.
  return FLAG_LABEL[flag] ?? flag
}
