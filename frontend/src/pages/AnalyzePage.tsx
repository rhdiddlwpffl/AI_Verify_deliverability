import { useState } from 'react'
import { analyze } from '../api/client'
import type { AnalyzeResponse } from '../api/types'
import { Disclaimer } from '../components/Disclaimer'
import { HistoryPanel } from '../components/HistoryPanel'
import { InputBox } from '../components/InputBox'
import { ResultView } from '../components/ResultView'
import { SaveNotice } from '../components/SaveNotice'

// 화면 상태를 하나로 묶어 둔다. (대기 / 분석 중 / 오류 / 완료)
type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; submittedText: string; result: AnalyzeResponse }

type Tab = 'new' | 'history'

export function AnalyzePage() {
  const [tab, setTab] = useState<Tab>('new')
  const [text, setText] = useState('')
  // 저장은 기본 꺼짐. 사용자가 체크해야 입력 원문이 서버에 저장된다. (선택을 다음 방문에 기억하지도 않는다)
  const [save, setSave] = useState(false)
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  async function run() {
    const submittedText = text // 분석 중에 입력창을 고쳐도 결과는 요청했던 원문 기준으로 보여 준다.
    setStatus({ kind: 'loading' })
    try {
      const result = await analyze(submittedText, save)
      setStatus({ kind: 'done', submittedText, result })
    } catch (e) {
      setStatus({
        kind: 'error',
        message: e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.',
      })
    }
  }

  return (
    <main className="page">
      <header>
        <h1>Answer Auditor</h1>
        <p className="muted">AI 답변에서 다시 확인해 볼 문장을 찾아 표시합니다.</p>
      </header>

      <Disclaimer />

      <nav className="tabs" aria-label="화면 선택">
        <button type="button" aria-pressed={tab === 'new'} onClick={() => setTab('new')}>
          새 분석
        </button>
        <button type="button" aria-pressed={tab === 'history'} onClick={() => setTab('history')}>
          내 기록
        </button>
      </nav>

      {/* '새 분석'은 숨기기만 해서, 기록을 보고 돌아와도 입력과 결과가 그대로 남아 있게 한다. */}
      <div hidden={tab !== 'new'}>
        <InputBox
          value={text}
          onChange={setText}
          save={save}
          onSaveChange={setSave}
          onSubmit={() => void run()}
          loading={status.kind === 'loading'}
        />

        {/* 상태 안내는 스크린 리더에도 읽히도록 live region 안에 둔다. */}
        <div aria-live="polite">
          {status.kind === 'loading' && (
            <p className="status">
              분석 중입니다… 문장을 분류하고, 위키백과에서 근거를 찾고, 비교하느라 보통 10~20초 걸립니다.
            </p>
          )}
          {status.kind === 'error' && (
            <div role="alert" className="error">
              <p>⚠️ {status.message}</p>
              <button type="button" onClick={() => void run()}>
                다시 시도
              </button>
            </div>
          )}
        </div>

        {status.kind === 'done' && (
          <>
            <SaveNotice status={status.result.save_status} />
            <ResultView submittedText={status.submittedText} result={status.result} />
          </>
        )}
      </div>

      {tab === 'history' && <HistoryPanel />}
    </main>
  )
}
