import { useEffect, useState } from 'react'
import { getHealth, type HealthResponse } from './api/client'

// 화면이 가질 수 있는 상태를 하나로 묶어 둔다. (로딩 / 성공 / 오류)
type HealthState =
  | { kind: 'loading' }
  | { kind: 'ok'; data: HealthResponse }
  | { kind: 'error'; message: string }

// 서버 상태를 확인하고 결과를 화면 상태로 바꿔 돌려준다. (예외를 던지지 않는다)
async function fetchHealthState(): Promise<HealthState> {
  try {
    return { kind: 'ok', data: await getHealth() }
  } catch (e) {
    return {
      kind: 'error',
      message: e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.',
    }
  }
}

function App() {
  // 초기값이 이미 '로딩'이므로, 처음 열릴 때는 따로 로딩 상태를 설정하지 않는다.
  const [state, setState] = useState<HealthState>({ kind: 'loading' })

  useEffect(() => {
    // 화면이 닫히거나 effect가 다시 실행되면 늦게 도착한 응답을 무시한다.
    let cancelled = false
    void fetchHealthState().then((next) => {
      if (!cancelled) setState(next)
    })
    return () => {
      cancelled = true
    }
  }, [])

  function retry() {
    setState({ kind: 'loading' })
    void fetchHealthState().then(setState)
  }

  return (
    <main style={{ maxWidth: 560, margin: '4rem auto', padding: '0 1rem' }}>
      <h1>Answer Auditor</h1>
      <p>AI 답변 검증기 — 백엔드 연결 확인</p>

      {state.kind === 'loading' && <p>서버에 연결하는 중…</p>}
      {state.kind === 'ok' && (
        <p>
          ✅ 서버 연결됨 (status: {state.data.status}, env: {state.data.env})
        </p>
      )}
      {state.kind === 'error' && (
        <div role="alert">
          <p>⚠️ {state.message}</p>
          <button type="button" onClick={retry}>
            다시 시도
          </button>
        </div>
      )}
    </main>
  )
}

export default App
