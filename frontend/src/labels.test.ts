// 이 서비스의 핵심 원칙: 검색된 출처 기준의 참고 정보이며, 사실 여부를 '확정 판정'처럼 표현하지 않는다.
// 화면에 쓰는 이름에 확정 표현이 들어가는 순간 이 테스트가 실패한다.
import { describe, expect, it } from 'vitest'
import {
  CLAIM_TYPE_LABEL,
  CONFIDENCE_LABEL,
  STANCE_LABEL,
  SUMMARY_LABEL,
  VERIFICATION_LABEL,
  claimTypeLabel,
  flagLabel,
  unverifiedMessage,
} from './labels'

// 참/거짓/정확/틀림/맞음/옳음/진실: 판정처럼 읽히는 글자. 상태 이름에는 한 글자도 들어가면 안 된다.
const DEFINITIVE = /참|거짓|정확|틀|맞|옳|진실/

const FLAGS = [
  'absolute_expression', 'contains_number', 'contains_year', 'vague_attribution', 'quotation',
  'overgeneralization', 'unverifiable_specificity', 'causal_claim', 'possibly_outdated',
]

describe('상태와 신호의 화면 이름', () => {
  it('어떤 이름에도 사실 여부를 단정하는 글자가 없다', () => {
    const all = [
      ...Object.values(VERIFICATION_LABEL),
      ...Object.values(SUMMARY_LABEL),
      ...Object.values(STANCE_LABEL),
      ...Object.values(CONFIDENCE_LABEL),
      ...Object.values(CLAIM_TYPE_LABEL),
      ...FLAGS.map(flagLabel),
    ]
    for (const label of all) expect(label, `"${label}"에 판정처럼 읽히는 글자가 있습니다`).not.toMatch(DEFINITIVE)
  })

  it('뒷받침/상충/엇갈림은 "검색된 출처 기준"임이 이름에 드러난다', () => {
    for (const status of ['supported', 'contradicted', 'mixed'] as const) {
      expect(VERIFICATION_LABEL[status]).toContain('검색된 출처')
    }
    expect(VERIFICATION_LABEL.supported).toContain('뒷받침하는 내용 발견')
    expect(VERIFICATION_LABEL.contradicted).toContain('상충하는 내용 발견')
  })

  it('"근거 부족", "검색 실패", "검증하지 못함"은 서로 다른 말이다 (없다는 것과 확인하지 못했다는 것은 다르다)', () => {
    expect(VERIFICATION_LABEL.insufficient).toContain('근거 부족')
    expect(VERIFICATION_LABEL.search_failed).toContain('검색 실패')
    expect(VERIFICATION_LABEL.search_failed).not.toContain('근거 부족')
    expect(VERIFICATION_LABEL.unverified).not.toContain('근거 부족')
    expect(VERIFICATION_LABEL.unverified).not.toContain('검색 실패')
  })

  it('상태 이름이 서로 겹치지 않는다', () => {
    const labels = Object.values(VERIFICATION_LABEL)
    expect(new Set(labels).size).toBe(labels.length)
  })

  it('문장 유형 이름이 "사실인 주장"으로 읽히지 않는다', () => {
    expect(CLAIM_TYPE_LABEL.factual).toBe('사실관계 주장')
  })

  it('모르는 값이 와도 깨지지 않는다 (서버에 값이 추가된 경우)', () => {
    expect(claimTypeLabel('brand_new_type')).toBe('기타')
    expect(flagLabel('brand_new_flag')).toBe('brand_new_flag')
  })
})

describe('비교하지 못한 이유 안내', () => {
  it('개수 제한과 비교 실패는 다른 문구이고, 둘 다 판정 표현이 없다', () => {
    const skipped = unverifiedMessage('skipped')
    const failed = unverifiedMessage('judge_failed')
    expect(skipped).not.toBe(failed)
    expect(skipped).toContain('제한')
    expect(failed).toContain('비교에 실패')
    expect(skipped).not.toMatch(DEFINITIVE)
    expect(failed).not.toMatch(DEFINITIVE)
    expect(unverifiedMessage(null)).toBe(failed) // 이유를 모르면 일반 실패 문구
  })
})
