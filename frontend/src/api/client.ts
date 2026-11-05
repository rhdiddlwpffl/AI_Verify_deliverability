// 백엔드 주소는 환경변수(VITE_API_BASE_URL)로 받는다.
// 로컬 개발(npm run dev)에서만 값이 없을 때 localhost:8000을 쓰고,
// 배포 빌드에서 값이 없으면 조용히 localhost로 가지 않고 오류로 드러낸다.
const API_BASE_URL: string | undefined =
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? 'http://localhost:8000' : undefined)

export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError('API 주소(VITE_API_BASE_URL)가 설정되지 않았습니다.')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`)
  } catch {
    // 서버가 꺼져 있거나, 네트워크/CORS 문제일 때 fetch 자체가 실패한다.
    throw new ApiError('서버에 연결할 수 없습니다. 서버 실행 여부와 CORS 설정을 확인하세요.')
  }

  if (!response.ok) {
    throw new ApiError(`서버가 오류를 반환했습니다. (HTTP ${response.status})`)
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
