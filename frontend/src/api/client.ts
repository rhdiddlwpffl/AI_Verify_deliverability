import type { AnalyzeResponse } from './types'

// 백엔드 주소는 환경변수(VITE_API_BASE_URL)로 받는다.
// 로컬 개발(npm run dev)에서만 값이 없을 때 localhost:8000을 쓰고,
// 배포 빌드에서 값이 없으면 조용히 localhost로 가지 않고 오류로 드러낸다.
const API_BASE_URL: string | undefined =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? 'http://localhost:8000' : undefined)

// 분석 요청 제한 시간. Claude 호출(수 초)과 배포 서버가 깨어나는 시간을 감안해 넉넉하게 둔다.
const REQUEST_TIMEOUT_MS = 90_000

export class ApiError extends Error {
  // 서버가 준 오류 코드(예: 'input_too_long'). 서버와 통신하지 못한 경우는 'network_error' 등 클라이언트 코드.
  code: string
  status: number | null

  constructor(message: string, code = 'client_error', status: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** 서버의 오류 응답 {"error": {"code", "message"}} 에서 값을 꺼낸다. 형식이 다르면 null. */
function parseServerError(body: unknown): { code: string; message: string } | null {
  if (typeof body !== 'object' || body === null || !('error' in body)) return null
  const error = (body as { error: unknown }).error
  if (typeof error !== 'object' || error === null) return null
  const { code, message } = error as { code?: unknown; message?: unknown }
  return typeof code === 'string' && typeof message === 'string' ? { code, message } : null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError('API 주소(VITE_API_BASE_URL)가 설정되지 않았습니다.', 'not_configured')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'TimeoutError') {
      throw new ApiError('응답이 너무 오래 걸립니다. 잠시 후 다시 시도해 주세요.', 'timeout')
    }
    // 서버가 꺼져 있거나, 네트워크/CORS 문제일 때 fetch 자체가 실패한다.
    throw new ApiError(
      '서버에 연결할 수 없습니다. 인터넷 연결을 확인하고 잠시 후 다시 시도해 주세요.',
      'network_error',
    )
  }

  if (!response.ok) {
    let body: unknown = null
    try {
      body = await response.json()
    } catch {
      // JSON이 아닌 응답(프록시 오류 페이지 등)
    }
    const serverError = parseServerError(body)
    if (serverError) throw new ApiError(serverError.message, serverError.code, response.status)
    throw new ApiError(`서버가 오류를 반환했습니다. (HTTP ${response.status})`, 'http_error', response.status)
  }
  return (await response.json()) as T
}

export interface HealthResponse {
  status: string
  env: string
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health')
}

export function analyze(text: string): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>('/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}
