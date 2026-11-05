import type { Claim } from '../api/types'
import { CONFIDENCE_LABEL, VERIFICATION_LABEL, unverifiedMessage } from '../labels'

// '검색된 출처 기준'의 참고용 상태. 사실 여부의 확정 판정이 아니다.
export function VerificationBox({ claim }: { claim: Claim }) {
  const status = claim.verification_status
  if (status === 'not_checkable') return null

  const showStrength =
    claim.verification_confidence !== null &&
    (status === 'supported' || status === 'contradicted' || status === 'mixed')

  return (
    <div className="verification">
      <p className={`vbadge vbadge--${status}`}>{VERIFICATION_LABEL[status] ?? status}</p>

      {status === 'unverified' && <p className="muted">{unverifiedMessage(claim.verification_error)}</p>}

      {claim.verification_rationale && (
        <p className="verification__rationale">비교 요약: {claim.verification_rationale}</p>
      )}

      {showStrength && claim.verification_confidence && (
        <p className="muted verification__strength">
          근거 강도: {CONFIDENCE_LABEL[claim.verification_confidence]}{' '}
          <span>(검증된 인용이 몇 건인지에 따른 값이며, 사실 여부의 확실성이 아닙니다)</span>
        </p>
      )}
    </div>
  )
}
