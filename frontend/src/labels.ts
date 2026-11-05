import type { ClaimType, Stance, VerificationStatus } from './api/types'

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

// 검증 상태의 화면 표시 이름. 모두 '검색된 출처 기준'이며 사실 여부의 확정 판정이 아니다.
// (supported를 '맞음', contradicted를 '틀림'으로 표시하지 않는다)
export const VERIFICATION_LABEL: Record<VerificationStatus, string> = {
  supported: '검색된 출처에서 뒷받침하는 내용 발견',
  contradicted: '검색된 출처와 상충하는 내용 발견',
  mixed: '검색된 출처 간 내용이 엇갈림',
  insufficient: '근거 부족 — 검색된 출처에서 확인하지 못함',
  search_failed: '검색 실패 — 확인하지 못함',
  unverified: '검증하지 못함',
  not_checkable: '검증 대상 아님',
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
}

export const STANCE_LABEL: Record<Stance, string> = {
  supports: '뒷받침하는 내용',
  contradicts: '상충하는 내용',
  neutral: '관련 내용 없음',
}

// unverified의 이유별 안내. '근거 부족'과 달리 비교 자체를 하지 못한 경우다.
export function unverifiedMessage(error: string | null): string {
  if (error === 'skipped') return '한 번에 검증하는 문장 수 제한 때문에 이 문장은 검증하지 않았습니다.'
  return '근거 비교에 실패했습니다. 아래 문서를 직접 확인하거나 잠시 후 다시 분석해 주세요.'
}

export function claimTypeLabel(type: string): string {
  return CLAIM_TYPE_LABEL[type as ClaimType] ?? '기타'
}

export function flagLabel(flag: string): string {
  // 서버에 새 신호가 추가돼도 화면이 깨지지 않도록 모르는 값은 그대로 보여 준다.
  return FLAG_LABEL[flag] ?? flag
}
