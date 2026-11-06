import { describe, expect, it } from 'vitest'
import { normalizeBaseUrl } from './client'

describe('API 주소 정리', () => {
  it('끝의 슬래시를 지운다 (남기면 //analyses 가 되어 404)', () => {
    expect(normalizeBaseUrl('https://api.example.com/')).toBe('https://api.example.com')
    expect(normalizeBaseUrl('https://api.example.com///')).toBe('https://api.example.com')
  })

  it('이미 깨끗한 주소와 앞뒤 공백을 처리한다', () => {
    expect(normalizeBaseUrl('https://api.example.com')).toBe('https://api.example.com')
    expect(normalizeBaseUrl('  https://api.example.com/  ')).toBe('https://api.example.com')
  })

  it('비어 있으면 설정 안 됨(undefined)으로 본다', () => {
    expect(normalizeBaseUrl(undefined)).toBeUndefined()
    expect(normalizeBaseUrl('')).toBeUndefined()
    expect(normalizeBaseUrl('   ')).toBeUndefined()
  })
})
