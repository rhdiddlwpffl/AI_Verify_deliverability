import type { Claim } from '../api/types'

export type Segment =
  | { kind: 'plain'; text: string }
  | { kind: 'claim'; text: string; claim: Claim }

/**
 * 원문을 '일반 글자'와 '분석된 문장' 조각으로 나눈다. (하이라이트용)
 *
 * 서버가 준 위치(start/end)가 원문과 어긋나면(겹침, 범위 초과, 글자 불일치) null 을 돌려준다.
 * 그 경우 호출하는 쪽은 하이라이트 없이 원문만 보여 줘야 한다. 엉뚱한 곳을 칠하는 것보다 낫다.
 */
export function buildSegments(text: string, claims: Claim[]): Segment[] | null {
  const segments: Segment[] = []
  let cursor = 0

  for (const claim of claims) {
    if (claim.start < cursor || claim.end > text.length || claim.start >= claim.end) return null
    if (text.slice(claim.start, claim.end) !== claim.text) return null

    if (claim.start > cursor) segments.push({ kind: 'plain', text: text.slice(cursor, claim.start) })
    segments.push({ kind: 'claim', text: claim.text, claim })
    cursor = claim.end
  }

  if (cursor < text.length) segments.push({ kind: 'plain', text: text.slice(cursor) })
  return segments
}
