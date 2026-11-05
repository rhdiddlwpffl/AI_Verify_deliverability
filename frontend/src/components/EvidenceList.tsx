import type { Claim } from '../api/types'

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

export function EvidenceList({ claim }: { claim: Claim }) {
  switch (claim.search_status) {
    case 'found':
      return (
        <div className="evidence">
          <p className="evidence__title">
            위키백과에서 찾은 관련 문서 <span className="muted">(검색어: {claim.search_query})</span>
          </p>
          <p className="muted evidence__note">
            검색된 문서일 뿐이며, 이 문장을 뒷받침하는지는 아직 판단하지 않았습니다.
          </p>
          <ul className="sources">
            {claim.sources.map((source) => (
              <li key={source.url} className="source">
                {isHttpsUrl(source.url) ? (
                  <a href={source.url} target="_blank" rel="noopener noreferrer">
                    {source.title}
                  </a>
                ) : (
                  <span>{source.title}</span>
                )}
                <p className="source__snippet">{source.snippet}</p>
              </li>
            ))}
          </ul>
          <p className="muted evidence__license">출처: 위키백과 (CC BY-SA 4.0)</p>
        </div>
      )
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
      return (
        <p className="evidence muted">
          한 번에 검색하는 문장 수 제한 때문에 이 문장은 검색하지 않았습니다.
        </p>
      )
    default:
      return null
  }
}
