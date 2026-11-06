import { describe, expect, it } from 'vitest'
import { makeClaim } from '../test-helpers'
import { buildSegments } from './segments'

// start/end는 서버가 JavaScript의 text.slice()와 맞게(UTF-16 기준) 내려 주는 값이다.
const TEXT = '😀 에펠탑은 1889년에 지어졌다. 이 문장은 평범하다. 정말 멋지다.'

function claimFor(sentence: string, idx: number) {
  const start = TEXT.indexOf(sentence)
  return makeClaim({ idx, text: sentence, start, end: start + sentence.length })
}

describe('buildSegments', () => {
  const claims = [claimFor('에펠탑은 1889년에 지어졌다.', 0), claimFor('정말 멋지다.', 2)]

  it('조각을 이어 붙이면 원문과 정확히 같다 (이모지 포함)', () => {
    const segments = buildSegments(TEXT, claims)
    expect(segments).not.toBeNull()
    expect(segments!.map((s) => s.text).join('')).toBe(TEXT)
  })

  it('문장 조각과 일반 글자 조각이 번갈아 나온다', () => {
    const kinds = buildSegments(TEXT, claims)!.map((s) => s.kind)
    expect(kinds).toEqual(['plain', 'claim', 'plain', 'claim'])
  })

  it('이모지 때문에 JavaScript 길이가 글자 수와 다르다는 점을 위치가 이미 반영하고 있다', () => {
    expect(TEXT.length).toBeGreaterThan(Array.from(TEXT).length)
    expect(buildSegments(TEXT, claims)).not.toBeNull()
  })

  it('문장이 없으면 원문 전체가 일반 조각 하나다', () => {
    expect(buildSegments('abc', [])).toEqual([{ kind: 'plain', text: 'abc' }])
    expect(buildSegments('', [])).toEqual([])
  })

  it('위치가 한 칸만 밀려도 칠하지 않고 null을 돌려준다 (엉뚱한 곳을 칠하지 않는다)', () => {
    const shifted = claims.map((c) => ({ ...c, start: c.start + 1, end: c.end + 1 }))
    expect(buildSegments(TEXT, shifted)).toBeNull()
  })

  it('겹치거나, 범위를 벗어나거나, 길이가 0이면 null이다', () => {
    expect(buildSegments(TEXT, [claims[0], { ...claims[0] }])).toBeNull()
    expect(buildSegments(TEXT, [{ ...claims[0], end: TEXT.length + 5 }])).toBeNull()
    expect(buildSegments(TEXT, [{ ...claims[0], start: 5, end: 5, text: '' }])).toBeNull()
  })

  it('서버가 준 문장 글자가 원문과 다르면 null이다', () => {
    expect(buildSegments(TEXT, [{ ...claims[0], text: '다른 문장입니다.' }])).toBeNull()
  })

  it('문장이 원문 맨 앞과 맨 끝에 붙어 있어도 빈 조각을 만들지 않는다', () => {
    const text = '앞 문장. 뒤 문장.'
    const segments = buildSegments(text, [claimFor2(text, '앞 문장.', 0), claimFor2(text, '뒤 문장.', 1)])!
    expect(segments.map((s) => s.kind)).toEqual(['claim', 'plain', 'claim'])
    expect(segments.every((s) => s.text.length > 0)).toBe(true)
  })
})

function claimFor2(text: string, sentence: string, idx: number) {
  const start = text.indexOf(sentence)
  return makeClaim({ idx, text: sentence, start, end: start + sentence.length })
}
