import { useEffect, useState } from 'react'
import { deleteAllAnalyses, deleteAnalysis, getAnalysis, listAnalyses } from '../api/client'
import { RETENTION_DAYS, type AnalysisDetail, type AnalysisSummary, type VerificationStatus } from '../api/types'
import { SUMMARY_LABEL, SUMMARY_ORDER } from '../labels'
import { isTokenPersistent } from '../lib/anonToken'
import { ResultView } from './ResultView'

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; items: AnalysisSummary[] }

type OpenState =
  | { kind: 'none' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'open'; detail: AnalysisDetail }

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : '알 수 없는 오류가 발생했습니다.'
}

// 예외를 던지지 않고 화면 상태로 바꿔 돌려준다.
async function fetchList(): Promise<ListState> {
  try {
    return { kind: 'ready', items: await listAnalyses() }
  } catch (e) {
    return { kind: 'error', message: messageOf(e) }
  }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' })
}

export function HistoryPanel() {
  const [list, setList] = useState<ListState>({ kind: 'loading' })
  const [opened, setOpened] = useState<OpenState>({ kind: 'none' })
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    // 탭을 열 때마다 새로 불러온다. 늦게 도착한 응답은 무시한다.
    let cancelled = false
    void fetchList().then((next) => {
      if (!cancelled) setList(next)
    })
    return () => {
      cancelled = true
    }
  }, [])

  function reload() {
    setList({ kind: 'loading' })
    void fetchList().then(setList)
  }

  async function open(id: string) {
    setActionError(null)
    setOpened({ kind: 'loading' })
    try {
      setOpened({ kind: 'open', detail: await getAnalysis(id) })
    } catch (e) {
      setOpened({ kind: 'error', message: messageOf(e) })
    }
  }

  async function remove(item: AnalysisSummary) {
    if (!window.confirm('이 기록을 삭제할까요? 되돌릴 수 없습니다.')) return
    setActionError(null)
    setBusy(true)
    try {
      await deleteAnalysis(item.id)
      setList((prev) => (prev.kind === 'ready' ? { kind: 'ready', items: prev.items.filter((i) => i.id !== item.id) } : prev))
      setOpened((prev) => (prev.kind === 'open' && prev.detail.id === item.id ? { kind: 'none' } : prev))
    } catch (e) {
      setActionError(messageOf(e))
    } finally {
      setBusy(false)
    }
  }

  async function removeAll() {
    if (!window.confirm('내 기록을 모두 삭제할까요? 입력 원문과 결과가 서버에서 지워지며 되돌릴 수 없습니다.')) return
    setActionError(null)
    setBusy(true)
    try {
      await deleteAllAnalyses()
      setList({ kind: 'ready', items: [] })
      setOpened({ kind: 'none' })
    } catch (e) {
      setActionError(messageOf(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="history-heading" className="history">
      <h2 id="history-heading">내 기록</h2>
      <p className="muted">
        이 브라우저에서 &apos;내 기록에 저장&apos;을 체크하고 분석한 결과입니다. 저장 후 {RETENTION_DAYS}일이 지나면
        자동으로 삭제됩니다.
      </p>
      {!isTokenPersistent() && (
        <p role="status" className="save-notice save-notice--warn">
          ⚠️ 이 브라우저는 데이터 저장을 허용하지 않아, 이 탭을 닫거나 새로고침하면 저장한 기록을 다시 볼 수 없습니다.
        </p>
      )}

      {list.kind === 'loading' && <p className="status">기록을 불러오는 중…</p>}

      {list.kind === 'error' && (
        <div role="alert" className="error">
          <p>⚠️ {list.message}</p>
          <button type="button" onClick={reload}>
            다시 시도
          </button>
        </div>
      )}

      {actionError && (
        <p role="alert" className="error">
          ⚠️ {actionError}
        </p>
      )}

      {list.kind === 'ready' && list.items.length === 0 && (
        <p className="muted">
          저장된 기록이 없습니다. 분석할 때 &apos;내 기록에 저장&apos;을 체크하면 여기에 쌓입니다.
        </p>
      )}

      {list.kind === 'ready' && list.items.length > 0 && (
        <>
          <ul className="history__list">
            {list.items.map((item) => (
              <li key={item.id} className="history__item">
                <p className="history__date muted">{formatDate(item.created_at)}</p>
                <p className="history__preview">{item.preview}</p>
                <p className="muted history__counts">
                  문장 {item.sentence_count}개 중 다시 확인해 볼 문장 {item.check_worthy_count}개
                  {SUMMARY_ORDER.filter((s) => item.status_counts[s]).map((s: VerificationStatus) => (
                    <span key={s} className="chip">
                      {SUMMARY_LABEL[s]} {item.status_counts[s]}
                    </span>
                  ))}
                </p>
                <div className="history__actions">
                  <button type="button" className="link-button" onClick={() => void open(item.id)}>
                    열기
                  </button>
                  <button type="button" className="link-button" disabled={busy} onClick={() => void remove(item)}>
                    삭제
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <button type="button" className="link-button" disabled={busy} onClick={() => void removeAll()}>
            내 기록 모두 삭제
          </button>
        </>
      )}

      <div aria-live="polite">
        {opened.kind === 'loading' && <p className="status">기록을 여는 중…</p>}
        {opened.kind === 'error' && (
          <p role="alert" className="error">
            ⚠️ {opened.message}
          </p>
        )}
      </div>

      {opened.kind === 'open' && (
        <div className="history__opened">
          <p className="muted">
            저장된 분석 · {formatDate(opened.detail.created_at)}{' '}
            <button type="button" className="link-button" onClick={() => setOpened({ kind: 'none' })}>
              닫기
            </button>
          </p>
          <ResultView key={opened.detail.id} submittedText={opened.detail.text} result={opened.detail.result} />
        </div>
      )}
    </section>
  )
}
