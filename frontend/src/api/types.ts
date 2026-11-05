// 백엔드 POST /analyses 의 요청/응답 형식. (backend/app/schemas/analysis.py 와 맞춘다)

export type ClaimType = 'factual' | 'numeric' | 'quote' | 'opinion' | 'other'

// not_searched: 확인 대상이 아님 / found: 관련 문서를 찾음 / none: 정상 검색, 결과 없음
// failed: 검색 자체가 실패 / skipped: 한 번에 검색하는 문장 수 제한으로 건너뜀
// 'none'과 'failed'는 전혀 다른 상황이다. (없다는 것과 확인하지 못했다는 것)
export type SearchStatus = 'not_searched' | 'found' | 'none' | 'failed' | 'skipped'

export type Stance = 'supports' | 'contradicts' | 'neutral'

// 검색된 출처 기준의 참고용 상태. 사실 여부의 확정 판정이 아니다.
// unverified: 개수 제한으로 건너뛰었거나 비교 호출이 실패해 비교하지 못함 ('근거 부족'과 다름)
export type VerificationStatus =
  | 'not_checkable'
  | 'supported'
  | 'contradicted'
  | 'mixed'
  | 'insufficient'
  | 'search_failed'
  | 'unverified'

// 검색으로 찾은 근거 후보 문서와, 그 발췌문을 주장과 비교한 결과
export interface Source {
  title: string
  url: string
  snippet: string
  source: string // 예: 'wikipedia-ko'
  // 비교하지 못했으면 null. supports/contradicts는 인용문이 발췌문에 실제로 있음을 서버가 확인한 경우에만 나온다.
  stance: Stance | null
  quote: string // 검증을 통과한 인용문. snippet 안의 실제 부분 문자열이라 indexOf로 찾을 수 있다. 없으면 ''
  downgraded: boolean // AI는 근거라고 했지만 검증을 통과하지 못해 제외한 경우
}

export interface Claim {
  idx: number
  text: string
  // 요청한 text 안에서의 위치. text.slice(start, end) 로 그대로 잘라 쓸 수 있다.
  start: number
  end: number
  claim_type: ClaimType
  check_worthy: boolean
  // 취약점 신호: '다시 확인해 볼 만한 특징'이지 거짓 판정이 아니다.
  flags: string[]
  reason: string
  search_status: SearchStatus
  search_query: string
  search_error: string | null // failed일 때: rate_limited | unavailable | timeout | error
  sources: Source[]
  verification_status: VerificationStatus
  // 검증된 인용이 몇 건인지에 따른 '근거 강도'. 사실 여부의 확실성이 아니다.
  verification_confidence: 'high' | 'medium' | 'low' | null
  verification_rationale: string | null // 발췌문에서 무엇이 확인/미확인인지 요약
  verification_error: string | null // unverified일 때: skipped | judge_failed | rate_limited | timeout | unavailable | error
}

export interface AnalyzeResponse {
  claims: Claim[]
  sentence_count: number
  check_worthy_count: number
  model: string
}

// 백엔드의 입력 상한과 같아야 한다. (서버는 '글자 수(코드 포인트)'로 센다)
export const MAX_INPUT_CHARS = 5000

/** 서버와 같은 방식으로 글자 수를 센다. (이모지 하나는 1글자. text.length 는 2로 세므로 쓰지 않는다) */
export function countChars(text: string): number {
  return Array.from(text).length
}
