import { useMemo } from 'react'
import type { Claim } from '../api/types'
import { buildSegments } from '../lib/segments'

interface Props {
  text: string // 분석을 요청했던 원문 (입력창의 현재 값이 아님)
  claims: Claim[]
  selectedIdx: number | null
  onSelect: (idx: number) => void
}

export function HighlightedText({ text, claims, selectedIdx, onSelect }: Props) {
  const segments = useMemo(() => buildSegments(text, claims), [text, claims])

  if (segments === null) {
    // 서버가 준 위치가 원문과 맞지 않는 예외 상황. 엉뚱한 곳을 칠하지 않고 원문만 보여 준다.
    return (
      <div>
        <p className="muted">문장 위치를 표시하지 못했습니다. 아래 목록에서 확인해 주세요.</p>
        <p className="answer-text">{text}</p>
      </div>
    )
  }

  return (
    <p className="answer-text">
      {segments.map((seg, i) => {
        if (seg.kind === 'plain') return <span key={i}>{seg.text}</span>
        const { claim } = seg
        // 확인 대상이 아닌 문장(제목, 의견 등)은 칠하지 않는다.
        if (!claim.check_worthy) return <span key={i}>{seg.text}</span>

        const flagged = claim.flags.length > 0
        const selected = claim.idx === selectedIdx
        const className = ['mark', flagged ? 'mark--flagged' : 'mark--check', selected ? 'mark--selected' : '']
          .filter(Boolean)
          .join(' ')
        return (
          <button
            key={i}
            id={`mark-${claim.idx}`}
            type="button"
            className={className}
            aria-pressed={selected}
            onClick={() => onSelect(claim.idx)}
          >
            {seg.text}
          </button>
        )
      })}
    </p>
  )
}
