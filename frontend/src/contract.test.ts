// 백엔드(파이썬)와 프론트(TypeScript)가 약속한 값이 어긋나지 않는지, 백엔드 소스를 직접 읽어서 확인한다.
// 상태, 신호, 유형을 하나 추가하고 한쪽만 고치는 실수가 가장 놓치기 쉽기 때문이다.
import { describe, expect, it } from 'vitest'
import raw_configPy from '../../backend/app/core/config.py?raw'
import raw_enumsPy from '../../backend/app/models/enums.py?raw'
import raw_analysesRoutePy from '../../backend/app/api/routes/analyses.py?raw'
import raw_schemaPy from '../../backend/app/schemas/analysis.py?raw'
import raw_evidencePy from '../../backend/app/services/evidence.py?raw'
import raw_rateLimitPy from '../../backend/app/services/rate_limit.py?raw'
import { RETENTION_DAYS, MAX_INPUT_CHARS } from './api/types'
import raw_typesTs from './api/types.ts?raw'
import raw_evidenceListTsx from './components/EvidenceList.tsx?raw'
import {
  CLAIM_TYPE_LABEL,
  CONFIDENCE_LABEL,
  STANCE_LABEL,
  SUMMARY_LABEL,
  VERIFICATION_LABEL,
  flagLabel,
} from './labels'
import raw_analyzePageTsx from './pages/AnalyzePage.tsx?raw'

// 줄바꿈이 CRLF든 LF든 읽히도록 정규화한다. (Windows에서 저장소를 새로 받으면 CRLF가 될 수 있다)
const normalize = (source: string) => source.replace(/\r\n/g, '\n')
const configPy = normalize(raw_configPy)
const enumsPy = normalize(raw_enumsPy)
const analysesRoutePy = normalize(raw_analysesRoutePy)
const schemaPy = normalize(raw_schemaPy)
const evidencePy = normalize(raw_evidencePy)
const rateLimitPy = normalize(raw_rateLimitPy)
const typesTs = normalize(raw_typesTs)
const evidenceListTsx = normalize(raw_evidenceListTsx)
const analyzePageTsx = normalize(raw_analyzePageTsx)

// ---------------------------------------------------------------- 소스 읽기 도우미

/** 파이썬 `class X(StrEnum):` 안의 `NAME = "value"` 값들 */
function pythonEnumValues(source: string, className: string): string[] {
  const lines = source.split('\n')
  const start = lines.findIndex((l) => l.startsWith(`class ${className}(`))
  if (start === -1) throw new Error(`백엔드에서 ${className} 클래스를 찾지 못했습니다.`)
  const values: string[] = []
  for (const line of lines.slice(start + 1)) {
    if (line.trim() !== '' && !line.startsWith(' ') && !line.startsWith('#')) break // 다음 최상위 코드
    const match = line.match(/^\s+[A-Z_]+ = "([^"]+)"/)
    if (match) values.push(match[1])
  }
  if (values.length === 0) throw new Error(`${className}에서 값을 하나도 읽지 못했습니다.`)
  return values
}

/** pydantic `class X(BaseModel):` 의 필드 이름들 */
function pydanticFields(source: string, className: string): string[] {
  const lines = source.split('\n')
  const start = lines.findIndex((l) => l.startsWith(`class ${className}(`))
  if (start === -1) throw new Error(`백엔드에서 ${className} 스키마를 찾지 못했습니다.`)
  const fields: string[] = []
  for (const line of lines.slice(start + 1)) {
    if (line.trim() !== '' && !line.startsWith(' ') && !line.startsWith('#')) break
    const match = line.match(/^ {4}(\w+): /)
    if (match) fields.push(match[1])
  }
  return fields
}

/** TypeScript `export interface X {` 의 필드 이름들 */
function tsInterfaceFields(source: string, name: string): string[] {
  const lines = source.split('\n')
  const start = lines.findIndex((l) => l.startsWith(`export interface ${name} {`))
  if (start === -1) throw new Error(`types.ts에서 ${name} 인터페이스를 찾지 못했습니다.`)
  const fields: string[] = []
  for (const line of lines.slice(start + 1)) {
    if (line === '}') break
    const match = line.match(/^ {2}(\w+)\??:/)
    if (match) fields.push(match[1])
  }
  return fields
}

/** TypeScript `export type X = 'a' | 'b'` 의 값들 (여러 줄 가능) */
function tsUnionValues(source: string, name: string): string[] {
  const match = source.match(new RegExp(`export type ${name} =([\\s\\S]*?)\\n\\n`))
  if (!match) throw new Error(`types.ts에서 ${name} 타입을 찾지 못했습니다.`)
  return [...match[1].matchAll(/'([^']+)'/g)].map((m) => m[1])
}

const sorted = (values: string[]) => [...values].sort()

// ---------------------------------------------------------------- 값 목록

describe('백엔드 enum과 프론트의 값/이름이 같다', () => {
  it('문장 유형(ClaimType): 타입 정의와 화면 이름이 모두 백엔드와 같다', () => {
    const backend = pythonEnumValues(enumsPy, 'ClaimType')
    expect(sorted(tsUnionValues(typesTs, 'ClaimType'))).toEqual(sorted(backend))
    expect(sorted(Object.keys(CLAIM_TYPE_LABEL))).toEqual(sorted(backend))
  })

  it('근거의 입장(Stance)', () => {
    const backend = pythonEnumValues(enumsPy, 'Stance')
    expect(sorted(tsUnionValues(typesTs, 'Stance'))).toEqual(sorted(backend))
    expect(sorted(Object.keys(STANCE_LABEL))).toEqual(sorted(backend))
  })

  it('검색 상태(SearchStatus)', () => {
    expect(sorted(tsUnionValues(typesTs, 'SearchStatus'))).toEqual(sorted(pythonEnumValues(enumsPy, 'SearchStatus')))
  })

  it('검증 상태(VerificationStatus): 타입, 상태 이름, 요약 이름이 모두 백엔드와 같다', () => {
    const backend = pythonEnumValues(enumsPy, 'VerificationStatus')
    expect(sorted(tsUnionValues(typesTs, 'VerificationStatus'))).toEqual(sorted(backend))
    expect(sorted(Object.keys(VERIFICATION_LABEL))).toEqual(sorted(backend))
    expect(sorted(Object.keys(SUMMARY_LABEL))).toEqual(sorted(backend))
  })

  it('근거 강도(Confidence)', () => {
    expect(sorted(Object.keys(CONFIDENCE_LABEL))).toEqual(sorted(pythonEnumValues(enumsPy, 'Confidence')))
  })

  it('백엔드가 내보낼 수 있는 취약점 신호마다 한국어 이름이 있다 (이름이 없으면 영어 코드가 그대로 보인다)', () => {
    for (const flag of pythonEnumValues(enumsPy, 'VulnerabilityFlag')) {
      expect(flagLabel(flag), `신호 ${flag}의 화면 이름이 없습니다`).not.toBe(flag)
    }
  })

  it('저장 상태(SaveStatus)의 값이 모두 백엔드 코드에 실제로 있다', () => {
    const backendSource = analysesRoutePy + schemaPy
    for (const value of tsUnionValues(typesTs, 'SaveStatus')) {
      expect(backendSource, `백엔드에 save_status "${value}"가 없습니다`).toContain(`"${value}"`)
    }
  })
})

// ---------------------------------------------------------------- 응답 필드

describe('백엔드 응답 스키마와 프론트 타입의 필드가 같다', () => {
  const pairs: [string, string][] = [
    ['ClaimOut', 'Claim'],
    ['SourceOut', 'Source'],
    ['AnalyzeResponse', 'AnalyzeResponse'],
    ['AnalysisSummaryOut', 'AnalysisSummary'],
    ['AnalysisDetail', 'AnalysisDetail'],
  ]
  for (const [backendName, frontendName] of pairs) {
    it(`${backendName} ↔ ${frontendName}`, () => {
      expect(sorted(tsInterfaceFields(typesTs, frontendName))).toEqual(sorted(pydanticFields(schemaPy, backendName)))
    })
  }
})

// ---------------------------------------------------------------- 두 곳에 있는 설정값

describe('두 곳에 적어 둔 값이 같다', () => {
  it('보관 기간: 화면 안내의 RETENTION_DAYS와 서버의 retention_days 기본값', () => {
    const backend = Number(configPy.match(/retention_days: int = (\d+)/)?.[1])
    expect(RETENTION_DAYS).toBe(backend)
  })

  it('입력 글자 수 상한', () => {
    expect(MAX_INPUT_CHARS).toBe(Number(configPy.match(/max_input_chars: int = (\d+)/)?.[1]))
  })
})

// ---------------------------------------------------------------- 오류 코드

describe('화면이 특별히 처리하는 오류 코드가 백엔드에 실제로 있다', () => {
  it('24시간 한도 오류: 이 코드일 때 "다시 시도" 버튼을 숨긴다', () => {
    const literal = analyzePageTsx.match(/DAILY_LIMIT_CODES = new Set\(\[([^\]]*)\]\)/)?.[1] ?? ''
    const codes = [...literal.matchAll(/'([^']+)'/g)].map((m) => m[1])
    expect(codes.length).toBeGreaterThan(0)
    for (const code of codes) expect(rateLimitPy, `백엔드에 오류 코드 "${code}"가 없습니다`).toContain(`"${code}"`)
  })

  it('검색 실패 이유: 백엔드가 만드는 모든 이유에 화면 안내가 있다', () => {
    const backendReasons = [...evidencePy.matchAll(/Evidence\(SearchStatus\.FAILED\.value, "(\w+)"\)/g)].map((m) => m[1])
    expect(backendReasons.length).toBeGreaterThan(0)
    const block = evidenceListTsx.match(/SEARCH_ERROR_MESSAGE[^{]*\{([\s\S]*?)\n\}/)?.[1] ?? ''
    const frontendKeys = [...block.matchAll(/^ {2}(\w+):/gm)].map((m) => m[1])
    for (const reason of backendReasons) {
      expect(frontendKeys, `검색 실패 이유 "${reason}"에 대한 화면 안내가 없습니다`).toContain(reason)
    }
  })
})
