import { useState } from 'react'
import type { AnalyzeResponse, VerificationStatus } from '../api/types'
import { ClaimCard } from './ClaimCard'
import { HighlightedText } from './HighlightedText'

const SUMMARY_ORDER: VerificationStatus[] = [
  'supported',
  'contradicted',
  'mixed',
  'insufficient',
  'search_failed',
  'unverified',
]
const SUMMARY_LABEL: Record<VerificationStatus, string> = {
  supported: '뒷받침하는 내용 발견',
  contradicted: '상충하는 내용 발견',
  mixed: '엇갈림',
  insufficient: '근거 부족',
  search_failed: '검색 실패',
  unverified: '검증하지 못함',
  not_checkable: '검증 대상 아님',
}

interface Props {
  submittedText: string // 분석을 요청했던 원문. 위치(start/end)는 이 글 기준이다.
  result: AnalyzeResponse
}

export function ResultView({ submittedText, result }: Props) {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const checkClaims = result.claims.filter((c) => c.check_worthy)
  const failedSearchCount = checkClaims.filter((c) => c.search_status === 'failed').length

  // 검증 상태별 문장 수 요약. 모두 '검색된 출처 기준'의 표현이며 참/거짓 집계가 아니다.
  const summaryParts = SUMMARY_ORDER.flatMap((status) => {
    const count = checkClaims.filter((c) => c.verification_status === status).length
    return count > 0 ? [`${SUMMARY_LABEL[status]} ${count}개`] : []
  })

  // 하이라이트를 누르면 해당 카드로, 카드의 버튼을 누르면 원문의 해당 문장으로 이동한다.
  function select(idx: number, scrollTo: 'card' | 'mark') {
    setSelectedIdx(idx)
    requestAnimationFrame(() => {
      document.getElementById(`${scrollTo}-${idx}`)?.scrollIntoView({ block: 'nearest' })
    })
  }

  return (
    <section aria-labelledby="result-heading" className="result">
      <h2 id="result-heading">분석 결과</h2>
      <p>
        문장 {result.sentence_count}개 중 <strong>다시 확인해 볼 문장 {result.check_worthy_count}개</strong>
      </p>
      {summaryParts.length > 0 && (
        <p className="muted" aria-label="검색된 출처 기준 요약">
          검색된 출처 기준: {summaryParts.join(' · ')}
        </p>
      )}
      {failedSearchCount > 0 && (
        <p role="status" className="muted">
          {failedSearchCount}개 문장은 검색에 실패해 근거 후보를 찾지 못했습니다. 잠시 후 다시 분석해 보세요.
        </p>
      )}

      <ul className="legend" aria-label="범례">
        <li>
          <span className="mark mark--check legend__sample">문장</span> 사실 확인이 필요한 주장
        </li>
        <li>
          <span className="mark mark--flagged legend__sample">문장</span> 확인이 필요하고, 다시 볼 만한 신호도 있음
        </li>
      </ul>

      <HighlightedText
        text={submittedText}
        claims={result.claims}
        selectedIdx={selectedIdx}
        onSelect={(idx) => select(idx, 'card')}
      />

      <h3>다시 확인해 볼 문장</h3>
      {checkClaims.length === 0 ? (
        <p className="muted">
          사실 확인이 필요한 주장을 찾지 못했습니다. 다만 이것이 내용이 모두 정확하다는 뜻은 아닙니다.
        </p>
      ) : (
        <ol className="cards">
          {checkClaims.map((claim) => (
            <ClaimCard
              key={claim.idx}
              claim={claim}
              selected={claim.idx === selectedIdx}
              onSelect={(idx) => select(idx, 'mark')}
            />
          ))}
        </ol>
      )}

      <p className="muted footnote">
        분류와 비교는 AI({result.model})가 했으며 틀릴 수 있습니다. 인용문이 발췌문에 실제로 있는지는
        프로그램이 확인하지만, 그 인용이 문장을 정말 뒷받침하는지는 직접 읽어 보셔야 합니다. 근거는
        위키백과(CC BY-SA 4.0) 문서의 앞부분(약 400자)만 사용하므로, 문서 뒷부분의 내용, 최근 사건,
        세부 통계는 &quot;근거 부족&quot;으로 나올 수 있습니다. 이는 사실 여부의 판정이 아닙니다.
      </p>
    </section>
  )
}
