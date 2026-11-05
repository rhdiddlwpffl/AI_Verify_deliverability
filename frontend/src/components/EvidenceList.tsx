import type { Claim } from '../api/types'
import { STANCE_LABEL } from '../labels'

// 검색이 실패한 이유별 안내. 모두 '근거가 부족하다'는 뜻이 아니라 '검색이 되지 않았다'는 뜻이다.
const SEARCH_ERROR_MESSAGE: Record<string, string> = {
  rate_limited: '검색 요청이 많아 검색하지 못했습니다. 잠시 후 다시 분석해 주세요.',
  unavailable: '검색 서버에 연결하지 못했습니다. 잠시 후 다시 분석해 주세요.',
  timeout: '검색이 오래 걸려 중단했습니다. 잠시 후 다시 분석해 주세요.',
  error: '검색에 실패했습니다. 잠시 후 다시 분석해 주세요.',
}

/** https 주소만 링크로 만든다. (서버가 준 값이라도 javascript: 같은 주소는 링크로 쓰지 않는다) */
function isHttpsUrl(url: string): boolean {
  return url.startsWith('https://')
}

/** 발췌문 안에서 검증된 인용문 부분을 강조한다. 인용문이 없거나 찾지 못하면 발췌문을 그대로 보여 준다. */
function Snippet({ text, quote }: { text: string; quote: string }) {
  const at = quote ? text.indexOf(quote) : -1
  if (at === -1) return <>{text}</>
  return (
    <>
      {text.slice(0, at)}
      <mark className="quote">{text.slice(at, at + quote.length)}</mark>
      {text.slice(at + quote.length)}
    </>
  )
}

export function EvidenceList({ claim }: { claim: Claim }) {
  switch (claim.search_status) {
    case 'found': {
      const compared = claim.sources.some((s) => s.stance !== null)
      return (
        <div className="evidence">
          <p className="evidence__title">
            위키백과에서 찾은 관련 문서 <span className="muted">(검색어: {claim.search_query})</span>
          </p>
          <p className="muted evidence__note">
            {compared
              ? 'AI가 발췌문과 문장을 비교했고, 표시된 인용문이 발췌문에 실제로 있는지는 프로그램이 확인했습니다. 그래도 틀릴 수 있으니 링크로 원문을 확인하세요.'
              : '근거 비교를 하지 못해 찾은 문서만 보여 드립니다. 이 문서가 문장을 뒷받침하는지는 직접 확인해 주세요.'}
          </p>
          <ul className="sources">
            {claim.sources.map((source) => (
              <li key={source.url} className="source">
                <div className="source__head">
                  {isHttpsUrl(source.url) ? (
                    <a href={source.url} target="_blank" rel="noopener noreferrer">
                      {source.title}
                    </a>
                  ) : (
                    <span>{source.title}</span>
                  )}
                  {source.stance && (
                    <span className={`stance stance--${source.stance}`}>{STANCE_LABEL[source.stance]}</span>
                  )}
                </div>
                {source.downgraded && (
                  <p className="muted source__note">
                    AI가 근거 후보로 봤지만 검증을 통과하지 못해(인용문 확인 불가, 또는 대상·시점 불일치) 근거에서
                    제외했습니다.
                  </p>
                )}
                <p className="source__snippet">
                  <Snippet text={source.snippet} quote={source.quote} />
                </p>
              </li>
            ))}
          </ul>
          <p className="muted evidence__license">출처: 위키백과 (CC BY-SA 4.0)</p>
        </div>
      )
    }
    case 'none':
      return (
        <p className="evidence muted">
          위키백과에서 관련 문서를 찾지 못했습니다 (검색어: {claim.search_query}). 찾지 못했다고 해서 틀린
          내용이라는 뜻은 아닙니다.
        </p>
      )
    case 'failed':
      return (
        <p className="evidence evidence--failed">
          {SEARCH_ERROR_MESSAGE[claim.search_error ?? 'error'] ?? SEARCH_ERROR_MESSAGE.error} 근거가
          부족하다는 뜻이 아니라 검색 자체가 되지 않은 것입니다.
        </p>
      )
    case 'skipped':
      return null // 안내는 검증 상태(VerificationBox)가 한 번만 보여 준다
    default:
      return null
  }
}
