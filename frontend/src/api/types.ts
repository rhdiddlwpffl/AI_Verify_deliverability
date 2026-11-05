// 백엔드 POST /analyses 의 요청/응답 형식. (backend/app/schemas/analysis.py 와 맞춘다)

export type ClaimType = 'factual' | 'numeric' | 'quote' | 'opinion' | 'other'

// not_searched: 확인 대상이 아님 / found: 관련 문서를 찾음 / none: 정상 검색, 결과 없음
// failed: 검색 자체가 실패 / skipped: 한 번에 검색하는 문장 수 제한으로 건너뜀
// 'none'과 'failed'는 전혀 다른 상황이다. (없다는 것과 확인하지 못했다는 것)
export type SearchStatus = 'not_searched' | 'found' | 'none' | 'failed' | 'skipped'

// 검색으로 찾은 근거 후보 문서. 이 문서가 주장을 뒷받침하는지는 아직 판단하지 않았다.
export interface Source {
  title: string
  url: string
  snippet: string
  source: string // 예: 'wikipedia-ko'
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
