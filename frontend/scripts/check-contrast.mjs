// index.css의 색 변수에서 WCAG 대비를 계산해 접근성 기준을 확인한다.
//   글자: 4.5:1 이상 / 입력창 테두리·상태 배지 테두리·포커스 링 같은 UI 경계: 3:1 이상
// 실행: node scripts/check-contrast.mjs   (frontend 폴더에서)
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf-8')

function parseVars(block) {
  const vars = {}
  for (const m of block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) vars[m[1]] = m[2]
  return vars
}

const darkStart = css.indexOf('@media (prefers-color-scheme: dark)')
const light = parseVars(css.slice(0, darkStart))
const dark = { ...light, ...parseVars(css.slice(darkStart)) } // 다크 모드는 라이트 값 위에 덮어쓴다

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const ratio = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

// [설명, 앞(글자/테두리) 변수, 뒤(배경) 변수, 최소 비율]
const TEXT = 4.5
const UI = 3
const pairs = [
  ['본문 글자', 'fg', 'bg', TEXT],
  ['카드 안 본문', 'fg', 'card', TEXT],
  ['보조 글자(muted) / 배경', 'muted', 'bg', TEXT],
  ['보조 글자(muted) / 카드', 'muted', 'card', TEXT],
  ['버튼 글자', 'accent-fg', 'accent', TEXT],
  ['링크(accent) / 배경', 'accent', 'bg', TEXT],
  ['링크(accent) / 카드', 'accent', 'card', TEXT],
  ['안내 상자 글자', 'fg', 'notice-bg', TEXT],
  ['오류 글자', 'error-fg', 'error-bg', TEXT],
  ['오류 글자 / 카드(검색 실패 문구)', 'error-fg', 'card', TEXT],
  ['확인 필요 하이라이트 글자', 'fg', 'mark-check-bg', TEXT],
  ['신호 있음 하이라이트 글자', 'fg', 'mark-flag-bg', TEXT],
  ['인용문 강조 글자', 'fg', 'quote-bg', TEXT],
  ['상태 배지 글자: 뒷받침', 'fg', 'status-supported-bg', TEXT],
  ['상태 배지 글자: 상충', 'fg', 'status-contradicted-bg', TEXT],
  ['상태 배지 글자: 엇갈림', 'fg', 'status-mixed-bg', TEXT],
  ['입력창/체크박스 테두리', 'control-border', 'bg', UI],
  ['탭 버튼 테두리(카드 배경)', 'control-border', 'card', UI],
  ['포커스 링', 'focus', 'bg', UI],
  ['상태 배지 테두리: 뒷받침', 'status-supported', 'bg', UI],
  ['상태 배지 테두리: 상충', 'status-contradicted', 'bg', UI],
  ['상태 배지 테두리: 엇갈림', 'status-mixed', 'bg', UI],
  ['하이라이트 밑줄', 'mark-line', 'mark-check-bg', UI],
  ['하이라이트 밑줄(신호 있음)', 'mark-line', 'mark-flag-bg', UI],
]

let failed = 0
for (const [name, vars] of [['라이트', light], ['다크', dark]]) {
  console.log(`\n[${name} 모드]`)
  for (const [label, fg, bg, min] of pairs) {
    if (!vars[fg] || !vars[bg]) {
      console.log(`  ??  ${label}: 변수 없음 (--${!vars[fg] ? fg : bg})`)
      failed++
      continue
    }
    const r = ratio(vars[fg], vars[bg])
    const ok = r >= min
    failed += !ok
    console.log(`  ${ok ? 'PASS' : 'FAIL'} ${r.toFixed(2).padStart(5)}:1 (기준 ${min}:1)  ${label}`)
  }
}
console.log(failed === 0 ? '\n모두 통과' : `\n실패/누락 ${failed}개`)
process.exit(failed === 0 ? 0 : 1)
