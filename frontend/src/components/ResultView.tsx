import { useState } from 'react'
import type { AnalyzeResponse } from '../api/types'
import { ClaimCard } from './ClaimCard'
import { HighlightedText } from './HighlightedText'

interface Props {
  submittedText: string // 분석을 요청했던 원문. 위치(start/end)는 이 글 기준이다.
  result: AnalyzeResponse
}

export function ResultView({ submittedText, result }: Props) {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const checkClaims = result.claims.filter((c) => c.check_worthy)
  const failedSearchCount = checkClaims.filter((c) => c.search_status === 'failed').length

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
        분류는 AI({result.model})가 했으며 틀릴 수 있습니다. 근거 후보는 위키백과(CC BY-SA 4.0) 검색
        결과이고, 표시는 &quot;확인해 볼 곳&quot;을 알려 줄 뿐 사실 여부를 판정하지 않습니다. 위키백과는
        백과사전이라 최근 사건이나 세부 통계는 찾지 못할 수 있습니다.
      </p>
    </section>
  )
}
