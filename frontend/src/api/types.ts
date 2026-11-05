// 백엔드 POST /analyses 의 요청/응답 형식. (backend/app/schemas/analysis.py 와 맞춘다)

export type ClaimType = 'factual' | 'numeric' | 'quote' | 'opinion' | 'other'

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
