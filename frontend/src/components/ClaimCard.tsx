import type { Claim } from '../api/types'
import { claimTypeLabel, flagLabel } from '../labels'
import { EvidenceList } from './EvidenceList'
import { VerificationBox } from './VerificationBox'

interface Props {
  claim: Claim
  selected: boolean
  onSelect: (idx: number) => void
}

export function ClaimCard({ claim, selected, onSelect }: Props) {
  return (
    <li id={`card-${claim.idx}`} className={selected ? 'card card--selected' : 'card'}>
      <p className="card__text">{claim.text}</p>

      <div className="card__meta">
        <span className="badge">{claimTypeLabel(claim.claim_type)}</span>
        {claim.flags.length === 0 ? (
          <span className="muted">특별히 표시된 취약점 신호는 없지만, 사실 확인 대상입니다.</span>
        ) : (
          <ul className="chips" aria-label="확인해 볼 점">
            {claim.flags.map((flag) => (
              <li key={flag} className="chip">
                {flagLabel(flag)}
              </li>
            ))}
          </ul>
        )}
      </div>

      <VerificationBox claim={claim} />

      {claim.reason && <p className="card__reason">분류 이유: {claim.reason}</p>}

      <EvidenceList claim={claim} />

      <button type="button" className="link-button" onClick={() => onSelect(claim.idx)}>
        원문에서 위치 보기
      </button>
    </li>
  )
}
