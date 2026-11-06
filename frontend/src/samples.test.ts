import { describe, expect, it } from 'vitest'
import { MAX_INPUT_CHARS, countChars } from './api/types'
import { SAMPLES } from './samples'

describe('샘플 답변', () => {
  it('입력 상한 안에 들어가고, 비어 있지 않다', () => {
    for (const sample of SAMPLES) {
      expect(sample.text.trim().length).toBeGreaterThan(0)
      expect(countChars(sample.text)).toBeLessThanOrEqual(MAX_INPUT_CHARS)
    }
  })

  it('id가 겹치지 않고 이름과 설명이 있다', () => {
    expect(new Set(SAMPLES.map((s) => s.id)).size).toBe(SAMPLES.length)
    for (const sample of SAMPLES) {
      expect(sample.label.length).toBeGreaterThan(0)
      expect(sample.description.length).toBeGreaterThan(0)
    }
  })

  it('틀린 내용을 섞은 예시가 "모든 오류를 잡는다"고 약속하지 않는다', () => {
    const wrong = SAMPLES.find((s) => s.id === 'wrong')
    expect(wrong?.description).toContain('모든 오류가 잡히는 것은 아닙니다')
  })
})
