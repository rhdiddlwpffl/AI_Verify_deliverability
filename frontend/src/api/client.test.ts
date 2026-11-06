import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fakeStorage } from '../test-helpers'
import { ApiError, analyze, deleteAllAnalyses, deleteAnalysis, getAnalysis, listAnalyses } from './client'

const TOKEN_PATTERN = /^[a-f0-9]{64}$/

type FetchArgs = [string, RequestInit]

function mockFetch(respond: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn(async (url: string, init: RequestInit) => respond(url, init))
  vi.stubGlobal('fetch', fn)
  return fn
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (e) {
    expect(e).toBeInstanceOf(ApiError)
    return e as ApiError
  }
  throw new Error('거부(reject)되어야 한다')
}

function headerOf(call: FetchArgs, name: string): string | undefined {
  return (call[1].headers as Record<string, string>)[name]
}

beforeEach(() => {
  vi.stubGlobal('localStorage', fakeStorage())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('요청 만들기', () => {
  it('저장하지 않는 분석에는 기록 식별 토큰을 보내지 않는다', async () => {
    const fn = mockFetch(() => json({ claims: [] }))
    await analyze('에펠탑은 1889년에 지어졌다.', false)
    const call = fn.mock.calls[0] as FetchArgs
    expect(call[0]).toBe('http://localhost:8000/analyses') // 로컬 개발에서만 쓰는 기본 주소
    expect(call[1].method).toBe('POST')
    expect(headerOf(call, 'X-Anon-Token')).toBeUndefined()
    expect(JSON.parse(call[1].body as string)).toEqual({ text: '에펠탑은 1889년에 지어졌다.', save: false })
  })

  it('저장하는 분석과 기록 API에는 같은 토큰을 헤더로 보낸다 (본문/주소에는 넣지 않는다)', async () => {
    const fn = mockFetch(() => json([]))
    await analyze('문장입니다.', true)
    await listAnalyses()
    const [saveCall, listCall] = fn.mock.calls as FetchArgs[]
    const token = headerOf(saveCall, 'X-Anon-Token')
    expect(token).toMatch(TOKEN_PATTERN)
    expect(headerOf(listCall, 'X-Anon-Token')).toBe(token)
    expect(saveCall[0]).not.toContain(token!)
    expect(saveCall[1].body as string).not.toContain(token!)
  })

  it('기록 조회/삭제는 올바른 방식과 주소로 보내고, id는 주소에 안전하게 인코딩한다', async () => {
    const fn = mockFetch(() => json({ deleted: 1 }))
    await getAnalysis('a/b?x=1')
    await deleteAnalysis('id-1')
    await deleteAllAnalyses()
    const calls = fn.mock.calls as FetchArgs[]
    expect(calls.map((c) => [c[1].method, c[0]])).toEqual([
      ['GET', 'http://localhost:8000/analyses/a%2Fb%3Fx%3D1'],
      ['DELETE', 'http://localhost:8000/analyses/id-1'],
      ['DELETE', 'http://localhost:8000/analyses'],
    ])
    expect(calls.every((c) => TOKEN_PATTERN.test(headerOf(c, 'X-Anon-Token') ?? ''))).toBe(true)
  })

  it('요청마다 제한 시간(AbortSignal)이 붙는다', async () => {
    const fn = mockFetch(() => json({}))
    await analyze('문장입니다.', false)
    expect((fn.mock.calls[0] as FetchArgs)[1].signal).toBeInstanceOf(AbortSignal)
  })
})

describe('오류 해석', () => {
  it('서버의 {error:{code,message}}를 그대로 ApiError로 만든다', async () => {
    mockFetch(() => json({ error: { code: 'daily_limit_reached', message: '24시간 사용 횟수를 모두 사용했습니다.' } }, 429))
    const error = await rejection(analyze('문장입니다.', false))
    expect(error).toMatchObject({ code: 'daily_limit_reached', status: 429, message: '24시간 사용 횟수를 모두 사용했습니다.' })
  })

  it('JSON이 아닌 응답(프록시 오류 페이지 등)은 상태 코드가 담긴 일반 오류가 된다', async () => {
    mockFetch(() => new Response('<html>Bad Gateway</html>', { status: 502 }))
    const error = await rejection(analyze('문장입니다.', false))
    expect(error).toMatchObject({ code: 'http_error', status: 502 })
    expect(error.message).toContain('502')
    expect(error.message).not.toContain('Bad Gateway') // 서버가 준 원문을 화면에 그대로 보여 주지 않는다
  })

  it('형식이 다른 JSON 오류도 일반 오류로 처리한다', async () => {
    mockFetch(() => json({ detail: 'Not Found' }, 404))
    expect(await rejection(analyze('문장입니다.', false))).toMatchObject({ code: 'http_error', status: 404 })
    mockFetch(() => json({ error: 'string' }, 500))
    expect(await rejection(analyze('문장입니다.', false))).toMatchObject({ code: 'http_error', status: 500 })
    mockFetch(() => json({ error: { code: 1, message: 2 } }, 500)) // 문자열이 아닌 값
    expect(await rejection(analyze('문장입니다.', false))).toMatchObject({ code: 'http_error' })
  })

  it('서버에 연결하지 못하면(꺼짐, 네트워크, CORS) network_error다', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    const error = await rejection(analyze('문장입니다.', false))
    expect(error).toMatchObject({ code: 'network_error', status: null })
    expect(error.message).toContain('서버에 연결할 수 없습니다')
  })

  it('제한 시간이 지나면 timeout이다', async () => {
    mockFetch(() => Promise.reject(new DOMException('timed out', 'TimeoutError')))
    expect(await rejection(analyze('문장입니다.', false))).toMatchObject({ code: 'timeout' })
  })

  it('성공 응답은 그대로 돌려준다', async () => {
    mockFetch(() => json({ claims: [], sentence_count: 0, check_worthy_count: 0, model: 'm', save_status: 'not_requested', analysis_id: null }))
    expect(await analyze('문장입니다.', false)).toMatchObject({ sentence_count: 0, save_status: 'not_requested' })
  })
})
