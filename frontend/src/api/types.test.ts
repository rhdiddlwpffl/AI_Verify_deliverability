import { describe, expect, it } from 'vitest'
import { MAX_INPUT_CHARS, countChars } from './types'

describe('countChars', () => {
  it('서버와 같은 방식으로 센다: 이모지 하나는 1글자다 (JavaScript length는 2)', () => {
    expect('😀'.length).toBe(2)
    expect(countChars('😀')).toBe(1)
    expect(countChars('a😀b')).toBe(3)
    expect(countChars('한글 abc')).toBe(6)
    expect(countChars('')).toBe(0)
  })

  it('이모지만으로 상한(5,000자)까지 채울 수 있다 (length로 세면 2,500자에서 막힌다)', () => {
    const text = '😀'.repeat(MAX_INPUT_CHARS)
    expect(countChars(text)).toBe(MAX_INPUT_CHARS)
    expect(text.length).toBe(MAX_INPUT_CHARS * 2)
  })

  it('상한은 서버의 MAX_INPUT_CHARS와 같은 5,000이다', () => {
    expect(MAX_INPUT_CHARS).toBe(5000)
  })
})
