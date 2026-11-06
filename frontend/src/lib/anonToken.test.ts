import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeStorage } from '../test-helpers'

const KEY = 'answer-auditor.anon-token'
const TOKEN_PATTERN = /^[a-f0-9]{64}$/

// 모듈 안에 토큰을 기억하는 변수가 있으므로, 시험마다 모듈을 새로 불러온다.
async function freshModule() {
  vi.resetModules()
  return await import('./anonToken')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('anonToken', () => {
  it('처음에는 64자 16진수(256비트) 토큰을 만들어 저장한다', async () => {
    const storage = fakeStorage()
    vi.stubGlobal('localStorage', storage)
    const { getAnonToken, isTokenPersistent } = await freshModule()
    const token = getAnonToken()
    expect(token).toMatch(TOKEN_PATTERN)
    expect(storage.data[KEY]).toBe(token)
    expect(isTokenPersistent()).toBe(true)
  })

  it('같은 값을 계속 쓰고, 새로 불러와도 저장된 값을 쓴다 (새로고침)', async () => {
    const storage = fakeStorage()
    vi.stubGlobal('localStorage', storage)
    const first = (await freshModule()).getAnonToken()
    expect((await freshModule()).getAnonToken()).toBe(first)
  })

  it('저장된 값이 손상됐거나 조작됐으면 버리고 새로 만든다', async () => {
    for (const bad of ['not-a-token', 'A'.repeat(64), 'a'.repeat(63), '', "' OR 1=1 --"]) {
      const storage = fakeStorage({ [KEY]: bad })
      vi.stubGlobal('localStorage', storage)
      const token = (await freshModule()).getAnonToken()
      expect(token).toMatch(TOKEN_PATTERN)
      expect(token).not.toBe(bad)
      expect(storage.data[KEY]).toBe(token)
    }
  })

  it('저장소가 막혀 있어도(시크릿 모드 등) 임시 토큰을 만들고, 저장되지 않음을 알린다', async () => {
    vi.stubGlobal('localStorage', fakeStorage({}, true))
    const { getAnonToken, isTokenPersistent } = await freshModule()
    const token = getAnonToken()
    expect(token).toMatch(TOKEN_PATTERN)
    expect(getAnonToken()).toBe(token) // 같은 탭에서는 같은 임시 토큰
    expect(isTokenPersistent()).toBe(false)
  })

  it('토큰은 매번 무작위다', async () => {
    vi.stubGlobal('localStorage', fakeStorage())
    const a = (await freshModule()).getAnonToken()
    vi.stubGlobal('localStorage', fakeStorage())
    const b = (await freshModule()).getAnonToken()
    expect(a).not.toBe(b)
  })
})
