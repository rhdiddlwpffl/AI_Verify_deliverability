// 테스트에서 쓰는 도우미. (제품 코드에서는 쓰지 않는다)
import type { Claim, Source } from './api/types'

export function makeSource(overrides: Partial<Source> = {}): Source {
  return {
    title: '에펠탑',
    url: 'https://ko.wikipedia.org/wiki/%EC%97%90%ED%8E%A0%ED%83%91',
    snippet: '에펠탑은 프랑스 파리에 위치한 격자형 철골 타워이다. 1889년에 건설되었다.',
    source: 'wikipedia-ko',
    stance: null,
    quote: '',
    downgraded: false,
    ...overrides,
  }
}

export function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    idx: 0,
    text: '에펠탑은 1889년에 지어졌다.',
    start: 0,
    end: 15,
    claim_type: 'numeric',
    check_worthy: true,
    flags: [],
    reason: '확인 가능한 수치 주장',
    search_status: 'not_searched',
    search_query: '에펠탑',
    search_error: null,
    sources: [],
    verification_status: 'not_checkable',
    verification_confidence: null,
    verification_rationale: null,
    verification_error: null,
    ...overrides,
  }
}

/** localStorage 흉내. throws=true이면 저장소가 막힌 브라우저(시크릿 모드 등)처럼 동작한다. */
export function fakeStorage(initial: Record<string, string> = {}, throws = false) {
  const data: Record<string, string> = { ...initial }
  return {
    data,
    getItem(key: string): string | null {
      if (throws) throw new Error('blocked')
      return key in data ? data[key] : null
    },
    setItem(key: string, value: string): void {
      if (throws) throw new Error('blocked')
      data[key] = value
    },
  }
}
