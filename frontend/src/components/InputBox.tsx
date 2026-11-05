import { MAX_INPUT_CHARS, countChars } from '../api/types'

interface Props {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  loading: boolean
}

export function InputBox({ value, onChange, onSubmit, loading }: Props) {
  const chars = countChars(value)
  const tooLong = chars > MAX_INPUT_CHARS
  const empty = value.trim() === ''

  return (
    <form
      className="input-box"
      onSubmit={(e) => {
        e.preventDefault()
        if (!loading && !tooLong && !empty) onSubmit()
      }}
    >
      <label htmlFor="answer-input">검증할 AI 답변을 붙여 넣으세요</label>
      <textarea
        id="answer-input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={10}
        placeholder="ChatGPT, Claude 등 AI가 쓴 답변을 여기에 붙여 넣습니다."
        aria-describedby="char-count"
        aria-invalid={tooLong}
      />
      <div className="input-box__footer">
        <span id="char-count" className={tooLong ? 'count count--over' : 'count'}>
          {chars.toLocaleString()} / {MAX_INPUT_CHARS.toLocaleString()}자
          {tooLong && ' — 너무 깁니다. 나누어 입력해 주세요.'}
        </span>
        <button type="submit" disabled={loading || tooLong || empty}>
          {loading ? '분석 중…' : '분석하기'}
        </button>
      </div>
    </form>
  )
}
