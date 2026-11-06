import { useState } from 'react'
import { ApiError, analyze } from '../api/client'
import type { AnalyzeResponse } from '../api/types'
import heroImage from '../assets/hero.png'
import { Disclaimer } from '../components/Disclaimer'
import { HistoryPanel } from '../components/HistoryPanel'
import { InputBox } from '../components/InputBox'
import { ResultView } from '../components/ResultView'
import { SaveNotice } from '../components/SaveNotice'

// 화면 상태를 하나로 묶어 둔다. (대기 / 분석 중 / 오류 / 완료)
type Status =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string; code: string | null }
  | { kind: 'done'; submittedText: string; result: AnalyzeResponse }

type Tab = 'new' | 'history'

// 서버가 24시간 사용 한도를 알려 주는 오류 코드. 이 경우에는 메시지에 대기 시간이 적혀 있다.
const DAILY_LIMIT_CODES = new Set(['daily_limit_reached', 'service_daily_limit'])

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
        code: e instanceof ApiError ? e.code : null,
      })
    }
  }

  return (
    <main className="page">
      <header className="site-header">
        <div>
          <h1>Answer Auditor</h1>
          <p className="muted">AI 답변에서 다시 확인해 볼 문장을 찾아 표시합니다.</p>
        </div>
        {/* 장식용 그림이라 대체 텍스트는 비워 둔다(스크린 리더가 읽지 않음) */}
        <img className="site-header__image" src={heroImage} alt="" width={112} height={112} />
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
              분석 중입니다… 문장을 분류하고, 위키백과에서 근거를 찾고, 비교하느라 보통 10~20초 걸립니다. 연달아 분석하면 위키백과 요청 속도 조절 때문에 최대 약 1분까지 걸릴 수 있습니다.
            </p>
          )}
          {status.kind === 'error' && (
            <div role="alert" className="error">
              <p>⚠️ {status.message}</p>
              {/* 24시간 한도를 모두 쓴 경우에는 바로 다시 시도해도 같은 결과라서 버튼을 보여 주지 않는다. */}
              {!DAILY_LIMIT_CODES.has(status.code ?? '') && (
                <button type="button" onClick={() => void run()}>
                  다시 시도
                </button>
              )}
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
