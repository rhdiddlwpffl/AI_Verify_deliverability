// 컴포넌트를 HTML 문자열로 그려서(react-dom/server) 화면에 나가는 글과 구조를 확인한다. (브라우저 없이)
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { AnalyzeResponse, Claim, SearchStatus, VerificationStatus } from '../api/types'
import { makeClaim, makeSource } from '../test-helpers'
import { ClaimCard } from './ClaimCard'
import { Disclaimer } from './Disclaimer'
import { EvidenceList } from './EvidenceList'
import { InputBox } from './InputBox'
import { ResultView } from './ResultView'
import { SaveNotice } from './SaveNotice'
import { VerificationBox } from './VerificationBox'

const html = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element)
const textOf = (markup: string) => markup.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ')

// 사실이나 거짓을 단정하는 '긍정문'. ("틀린 내용이라는 뜻은 아닙니다" 같은 부정/면책 문장은 걸리지 않는다)
const DEFINITIVE_STATEMENTS = [/사실입니다/, /거짓입니다/, /참입니다/, /정확합니다/, /맞습니다/, /틀렸습니다/, /틀린 내용입니다/, /오류입니다/, /거짓으로/, /진실/]

function expectNoDefinitiveStatements(markup: string, where: string) {
  for (const pattern of DEFINITIVE_STATEMENTS) {
    expect(textOf(markup), `${where}에 확정 표현 ${pattern}이(가) 있습니다`).not.toMatch(pattern)
  }
}

const SEARCH_STATUSES: SearchStatus[] = ['not_searched', 'found', 'none', 'failed', 'skipped']
const VERIFICATION_STATUSES: VerificationStatus[] = ['not_checkable', 'supported', 'contradicted', 'mixed', 'insufficient', 'search_failed', 'unverified']

describe('EvidenceList (검색된 근거)', () => {
  const found = makeClaim({
    search_status: 'found',
    verification_status: 'supported',
    sources: [
      makeSource({ stance: 'supports', quote: '1889년에 건설되었다.' }),
      makeSource({ title: '귀스타브 에펠', url: 'https://ko.wikipedia.org/wiki/x', stance: 'neutral', downgraded: true }),
    ],
  })

  it('찾은 문서는 제목 링크, 입장 이름, 출처 표기(CC BY-SA)와 함께 나온다', () => {
    const markup = html(createElement(EvidenceList, { claim: found }))
    expect(markup).toContain('위키백과에서 찾은 관련 문서')
    expect(markup).toContain('뒷받침하는 내용')
    expect(markup).toContain('관련 내용 없음')
    expect(markup).toContain('CC BY-SA 4.0')
    expect(markup).toContain('원문을 확인하세요')
  })

  it('검증된 인용문은 발췌문 안에서 강조되고, 찾지 못하면 강조하지 않는다', () => {
    expect(html(createElement(EvidenceList, { claim: found }))).toContain('<mark class="quote">1889년에 건설되었다.</mark>')
    const notFound = makeClaim({ search_status: 'found', sources: [makeSource({ stance: 'supports', quote: '발췌문에 없는 문장입니다.' })] })
    expect(html(createElement(EvidenceList, { claim: notFound }))).not.toContain('<mark')
  })

  it('근거에서 제외된 출처에는 제외 이유 안내가 붙는다', () => {
    expect(textOf(html(createElement(EvidenceList, { claim: found })))).toContain('근거에서 제외했습니다')
  })

  it('https가 아닌 주소(javascript: 등)는 링크로 만들지 않는다', () => {
    const evil = makeClaim({ search_status: 'found', sources: [makeSource({ url: 'javascript:alert(1)', title: '위험한 문서' })] })
    const markup = html(createElement(EvidenceList, { claim: evil }))
    expect(markup).toContain('위험한 문서')
    expect(markup).not.toContain('<a ')
    expect(markup).not.toContain('javascript:')
  })

  it('정상 링크는 새 창으로 열리고 opener를 넘기지 않는다', () => {
    const markup = html(createElement(EvidenceList, { claim: found }))
    expect(markup).toMatch(/<a href="https:\/\/ko\.wikipedia\.org[^"]*" target="_blank" rel="noopener noreferrer">/)
  })

  it('발췌문의 HTML 문자는 그대로 글자로 나온다 (스크립트가 실행되지 않는다)', () => {
    const xss = makeClaim({ search_status: 'found', sources: [makeSource({ snippet: '<script>alert(1)</script> 문서', title: '<img src=x onerror=alert(1)>' })] })
    const markup = html(createElement(EvidenceList, { claim: xss }))
    expect(markup).not.toContain('<script>')
    expect(markup).not.toContain('<img')
    expect(markup).toContain('&lt;script&gt;')
  })

  it('"찾지 못함"과 "검색 실패"와 "개수 제한"은 서로 다른 안내다', () => {
    const none = textOf(html(createElement(EvidenceList, { claim: makeClaim({ search_status: 'none' }) })))
    const failed = textOf(html(createElement(EvidenceList, { claim: makeClaim({ search_status: 'failed', search_error: 'rate_limited' }) })))
    expect(none).toContain('찾지 못했습니다')
    expect(none).toContain('틀린 내용이라는 뜻은 아닙니다') // 찾지 못한 것은 틀렸다는 뜻이 아니다
    expect(failed).toContain('검색 자체가 되지 않은 것')
    expect(failed).toContain('검색 요청이 많아') // 이유별 안내
    expect(failed).not.toContain('찾지 못했습니다')
    expect(html(createElement(EvidenceList, { claim: makeClaim({ search_status: 'skipped' }) }))).toBe('') // 안내는 검증 상태 쪽에서 한 번만
    expect(html(createElement(EvidenceList, { claim: makeClaim({ search_status: 'not_searched' }) }))).toBe('')
  })

  it('알 수 없는 검색 실패 이유도 일반 안내로 나온다', () => {
    const markup = textOf(html(createElement(EvidenceList, { claim: makeClaim({ search_status: 'failed', search_error: 'brand_new_reason' }) })))
    expect(markup).toContain('검색에 실패했습니다')
  })

  it('비교하지 못한 경우(stance 없음)에는 문서만 보여 준다고 알린다', () => {
    const uncompared = makeClaim({ search_status: 'found', sources: [makeSource({ stance: null })] })
    const markup = textOf(html(createElement(EvidenceList, { claim: uncompared })))
    expect(markup).toContain('근거 비교를 하지 못해')
    expect(markup).not.toContain('뒷받침하는 내용')
  })
})

describe('VerificationBox (검증 상태)', () => {
  it('확인 대상이 아니면 아무것도 그리지 않는다', () => {
    expect(html(createElement(VerificationBox, { claim: makeClaim({ verification_status: 'not_checkable' }) }))).toBe('')
  })

  it('상태마다 서로 다른 배지와 이름이 나온다', () => {
    const shown = VERIFICATION_STATUSES.filter((s) => s !== 'not_checkable').map((status) => {
      const markup = html(createElement(VerificationBox, { claim: makeClaim({ verification_status: status }) }))
      expect(markup).toContain(`vbadge--${status}`)
      return textOf(markup)
    })
    expect(new Set(shown).size).toBe(shown.length)
  })

  it('근거 강도는 뒷받침/상충/엇갈림에만 나오고, 사실 여부의 확실성이 아니라는 설명이 붙는다', () => {
    const supported = textOf(html(createElement(VerificationBox, { claim: makeClaim({ verification_status: 'supported', verification_confidence: 'high' }) })))
    expect(supported).toContain('근거 강도: 높음')
    expect(supported).toContain('사실 여부의 확실성이 아닙니다')
    const insufficient = textOf(html(createElement(VerificationBox, { claim: makeClaim({ verification_status: 'insufficient', verification_confidence: 'low' }) })))
    expect(insufficient).not.toContain('근거 강도')
  })

  it('비교 요약이 있으면 보여 준다', () => {
    const markup = textOf(html(createElement(VerificationBox, { claim: makeClaim({ verification_status: 'supported', verification_rationale: '발췌문에서 연도가 확인됨' }) })))
    expect(markup).toContain('비교 요약: 발췌문에서 연도가 확인됨')
  })

  it('검증하지 못한 이유(개수 제한/비교 실패)를 구분해서 알린다', () => {
    const skipped = textOf(html(createElement(VerificationBox, { claim: makeClaim({ verification_status: 'unverified', verification_error: 'skipped' }) })))
    const failed = textOf(html(createElement(VerificationBox, { claim: makeClaim({ verification_status: 'unverified', verification_error: 'judge_failed' }) })))
    expect(skipped).toContain('문장 수 제한')
    expect(failed).toContain('근거 비교에 실패했습니다')
  })
})

describe('ClaimCard', () => {
  it('유형, 취약점 신호, 분류 이유, 검증 상태, 근거가 한 카드에 나온다', () => {
    const claim = makeClaim({
      flags: ['contains_number', 'contains_year'],
      search_status: 'found',
      sources: [makeSource({ stance: 'supports', quote: '1889년에 건설되었다.' })],
      verification_status: 'supported',
      verification_confidence: 'medium',
    })
    const text = textOf(html(createElement(ClaimCard, { claim, selected: false, onSelect: () => {} })))
    for (const expected of ['수치 주장', '수치 포함', '연도 포함', '분류 이유', '검색된 출처에서 뒷받침하는 내용 발견', '위키백과에서 찾은 관련 문서']) {
      expect(text).toContain(expected)
    }
  })

  it('신호가 없으면 "신호는 없지만 확인 대상"이라고 알리고, 선택된 카드를 표시한다', () => {
    const markup = html(createElement(ClaimCard, { claim: makeClaim({ flags: [] }), selected: true, onSelect: () => {} }))
    expect(textOf(markup)).toContain('특별히 표시된 취약점 신호는 없지만')
    expect(markup).toContain('card--selected')
  })
})

describe('InputBox (입력과 개인정보 안내)', () => {
  const render = (overrides: Partial<Parameters<typeof InputBox>[0]> = {}) =>
    html(createElement(InputBox, { value: '', onChange: () => {}, save: false, onSaveChange: () => {}, onSubmit: () => {}, loading: false, ...overrides }))

  it('저장 체크박스는 기본으로 꺼져 있다', () => {
    const markup = render({ save: false })
    expect(markup).toMatch(/<input type="checkbox"(?![^>]*checked)[^>]*>/)
    expect(render({ save: true })).toMatch(/<input type="checkbox"[^>]*checked/)
  })

  it('입력이 AI 서비스(Anthropic)와 위키백과로 전송된다는 안내가 분석 전에 보인다', () => {
    const text = textOf(render())
    expect(text).toContain('Anthropic')
    expect(text).toContain('위키백과')
    expect(text).toContain('개인정보나 비밀 정보는 붙여 넣지 마세요')
  })

  it('저장하면 원문과 결과가 서버에 보관된다는 점과 보관 기간을 알린다', () => {
    const text = textOf(render())
    expect(text).toContain('서버 DB')
    expect(text).toContain('30일')
    expect(text).toContain('언제든 삭제')
  })

  it('입력이 비어 있거나 분석 중이거나 상한을 넘으면 분석 버튼이 꺼진다', () => {
    expect(render({ value: '' })).toMatch(/<button type="submit" disabled/)
    expect(render({ value: '문장입니다.', loading: true })).toMatch(/<button type="submit" disabled[^>]*>분석 중…/)
    expect(render({ value: 'a'.repeat(5001) })).toMatch(/<button type="submit" disabled/)
    expect(render({ value: '문장입니다.' })).not.toMatch(/<button type="submit" disabled/)
  })

  it('글자 수는 상한과 함께 보이고, 넘으면 경고 문구가 붙는다', () => {
    expect(textOf(render({ value: '😀😀' }))).toContain('2 / 5,000자') // 이모지는 1글자씩
    expect(textOf(render({ value: 'a'.repeat(5001) }))).toContain('너무 깁니다')
  })

  it('입력창에는 연결된 레이블이 있다', () => {
    const markup = render()
    expect(markup).toContain('for="answer-input"')
    expect(markup).toContain('id="answer-input"')
  })

  it('샘플 버튼이 있고, 샘플도 분석 횟수로 계산된다는 안내가 있다', () => {
    const markup = render()
    expect(markup).toContain('여러 분야가 섞인 답변')
    expect(markup).toContain('일부러 틀린 내용을 섞은 답변')
    expect(textOf(markup)).toContain('분석 1회로 계산됩니다')
  })
})

describe('안내와 요약', () => {
  it('상단 안내는 판정이 아니라는 점과 "검색된 출처 기준"임을 분명히 한다', () => {
    const text = textOf(html(createElement(Disclaimer)))
    expect(text).toContain('참고용 도구입니다')
    expect(text).toContain('확정하는 판정이 아닙니다')
    expect(text).toContain('검색된 출처 기준')
    expect(text).toContain('위키백과에서 찾지 못했다고 해서 틀린 것도 아닙니다')
  })

  it('저장 결과 안내: 저장 실패해도 분석 결과는 정상이라고 알린다', () => {
    expect(html(createElement(SaveNotice, { status: 'not_requested' }))).toBe('')
    expect(textOf(html(createElement(SaveNotice, { status: 'saved' })))).toContain('내 기록에 저장했습니다')
    expect(textOf(html(createElement(SaveNotice, { status: 'failed' })))).toContain('분석 결과는 정상')
    expect(textOf(html(createElement(SaveNotice, { status: 'no_token' })))).toContain('분석 결과는 정상')
  })
})

describe('ResultView (결과 화면)', () => {
  const text = '에펠탑은 1889년에 지어졌다. 정말 멋지다. 어제 서울에서 지진이 났다.'
  // 문장 위치는 손으로 세지 않고 원문에서 계산한다. (잘못 세면 하이라이트가 조용히 꺼져서 다른 검사가 의미 없어진다)
  const at = (sentence: string) => ({ text: sentence, start: text.indexOf(sentence), end: text.indexOf(sentence) + sentence.length })
  const claims: Claim[] = [
    makeClaim({ idx: 0, ...at('에펠탑은 1889년에 지어졌다.'), flags: ['contains_number'], search_status: 'found', verification_status: 'supported', sources: [makeSource({ stance: 'supports', quote: '1889년에 건설되었다.' })] }),
    makeClaim({ idx: 1, ...at('정말 멋지다.'), check_worthy: false, claim_type: 'opinion', verification_status: 'not_checkable' }),
    makeClaim({ idx: 2, ...at('어제 서울에서 지진이 났다.'), search_status: 'failed', search_error: 'unavailable', verification_status: 'search_failed' }),
  ]
  const result: AnalyzeResponse = { claims, sentence_count: 3, check_worthy_count: 2, model: 'claude-haiku-5-5', save_status: 'not_requested', analysis_id: null }

  it('시험 데이터의 위치가 원문과 맞다 (이게 틀리면 아래 하이라이트 검사가 의미가 없다)', () => {
    for (const c of claims) expect(text.slice(c.start, c.end)).toBe(c.text)
    expect(html(createElement(ResultView, { submittedText: text, result }))).not.toContain('문장 위치를 표시하지 못했습니다')
  })

  it('요약에 상태별 문장 수가 "검색된 출처 기준"으로 나오고, 검색 실패 개수를 따로 알린다', () => {
    const markup = textOf(html(createElement(ResultView, { submittedText: text, result })))
    expect(markup).toContain('문장 3개 중 다시 확인해 볼 문장 2개')
    expect(markup).toContain('검색된 출처 기준: 뒷받침하는 내용 발견 1개 · 검색 실패 1개')
    expect(markup).toContain('1개 문장은 검색에 실패해')
  })

  it('확인 대상이 아닌 문장은 카드로 나오지 않고, 확인 필요 문장만 칠해진다', () => {
    const markup = html(createElement(ResultView, { submittedText: text, result }))
    expect(markup.match(/class="card"/g)?.length).toBe(2)
    expect(markup.match(/class="mark mark--/g)?.length).toBe(2 + 2) // 본문의 문장 2개 + 범례 견본 2개
  })

  it('확인 필요 문장이 하나도 없어도 "모두 정확하다는 뜻은 아니다"라고 알린다', () => {
    const only = '정말 멋지다.'
    const none: AnalyzeResponse = { ...result, claims: [{ ...claims[1], start: 0, end: only.length }], sentence_count: 1, check_worthy_count: 0 }
    const markup = textOf(html(createElement(ResultView, { submittedText: only, result: none })))
    expect(markup).toContain('내용이 모두 정확하다는 뜻은 아닙니다')
  })

  it('서버가 준 위치가 원문과 맞지 않으면 칠하지 않고 안내한다', () => {
    const broken = { ...result, claims: claims.map((c) => ({ ...c, start: c.start + 3, end: c.end + 3 })) }
    const markup = textOf(html(createElement(ResultView, { submittedText: text, result: broken })))
    expect(markup).toContain('문장 위치를 표시하지 못했습니다')
  })

  it('하단 주석이 AI의 한계, 인용 검증의 한계, 근거 범위의 한계를 알린다', () => {
    const markup = textOf(html(createElement(ResultView, { submittedText: text, result })))
    expect(markup).toContain('틀릴 수 있습니다')
    expect(markup).toContain('직접 읽어 보셔야 합니다')
    expect(markup).toContain('앞부분(약 400자)')
    expect(markup).toContain('사실 여부의 판정이 아닙니다')
  })
})

describe('화면 어디에도 확정 판정 표현이 없다', () => {
  it('모든 검색 상태와 검증 상태의 조합을 그려서 검사한다', () => {
    for (const search_status of SEARCH_STATUSES) {
      for (const verification_status of VERIFICATION_STATUSES) {
        const claim = makeClaim({
          search_status,
          verification_status,
          verification_confidence: 'high',
          verification_rationale: '발췌문에서 연도가 확인됨',
          search_error: search_status === 'failed' ? 'timeout' : null,
          sources: [makeSource({ stance: 'supports', quote: '1889년에 건설되었다.' }), makeSource({ stance: 'contradicts', downgraded: true })],
        })
        const markup = html(createElement(ClaimCard, { claim, selected: false, onSelect: () => {} }))
        expectNoDefinitiveStatements(markup, `${search_status}/${verification_status}`)
      }
    }
  })

  it('안내문, 입력 화면, 결과 화면, 저장 안내', () => {
    expectNoDefinitiveStatements(html(createElement(Disclaimer)), 'Disclaimer')
    expectNoDefinitiveStatements(html(createElement(InputBox, { value: '', onChange: () => {}, save: false, onSaveChange: () => {}, onSubmit: () => {}, loading: false })), 'InputBox')
    for (const status of ['saved', 'failed', 'no_token'] as const) {
      expectNoDefinitiveStatements(html(createElement(SaveNotice, { status })), `SaveNotice/${status}`)
    }
  })
})

describe('분석 화면의 처음 상태', () => {
  it('내 기록 저장은 기본으로 꺼져 있다 (사용자가 정한 개인정보 기본값)', async () => {
    const { AnalyzePage } = await import('../pages/AnalyzePage')
    const markup = html(createElement(AnalyzePage))
    expect(markup).toMatch(/<input type="checkbox"(?![^>]*checked)[^>]*>/)
    expect(textOf(markup)).toContain('내 기록에 저장')
  })

  it('처음에는 "새 분석" 탭이 보이고, 상단 안내와 개인정보 안내가 함께 있다', async () => {
    const { AnalyzePage } = await import('../pages/AnalyzePage')
    const markup = html(createElement(AnalyzePage))
    expect(markup).toContain('aria-pressed="true">새 분석')
    expect(markup).toContain('aria-pressed="false">내 기록')
    expect(textOf(markup)).toContain('참고용 도구입니다')
    expect(textOf(markup)).toContain('Anthropic')
  })
})
