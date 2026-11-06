import { MAX_INPUT_CHARS, RETENTION_DAYS, countChars } from '../api/types'
import { SAMPLES } from '../samples'

interface Props {
  value: string
  onChange: (value: string) => void
  save: boolean
  onSaveChange: (save: boolean) => void
  onSubmit: () => void
  loading: boolean
}

export function InputBox({ value, onChange, save, onSaveChange, onSubmit, loading }: Props) {
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
        aria-describedby="char-count privacy-note"
        aria-invalid={tooLong}
      />

      <div className="samples">
        <span className="muted">예시로 해 보기:</span>
        {SAMPLES.map((sample) => (
          <button
            key={sample.id}
            type="button"
            className="link-button"
            title={sample.description}
            onClick={() => {
              // 이미 쓴 내용이 있으면 덮어쓰기 전에 확인한다.
              if (value.trim() !== '' && !window.confirm('입력창의 내용이 예시로 바뀝니다. 계속할까요?')) return
              onChange(sample.text)
            }}
          >
            {sample.label}
          </button>
        ))}
      </div>
      <p className="muted samples__note">
        예시도 분석 1회로 계산됩니다(호출 횟수 제한). 결과는 실행할 때마다 조금 다를 수 있고, 모든 오류를 잡아내는
        것은 아닙니다.
      </p>

      {/* 입력이 어디로 전송되는지는 분석 전에 보여야 한다. */}
      <p id="privacy-note" className="muted privacy-note">
        분석을 위해 입력한 글이 <strong>AI 서비스(Anthropic)</strong>로 전송되고, 검색어(핵심어)는{' '}
        <strong>위키백과</strong>로 전송됩니다. 개인정보나 비밀 정보는 붙여 넣지 마세요.
      </p>

      <label className="save-option">
        <input type="checkbox" checked={save} onChange={(e) => onSaveChange(e.target.checked)} />
        <span>
          <strong>내 기록에 저장</strong>
          <span className="muted">
            {' '}
            — 체크하면 입력 원문과 결과가 서버 DB에 {RETENTION_DAYS}일간 보관되고, 이 브라우저에서만 볼 수 있습니다.
            &apos;내 기록&apos;에서 언제든 삭제할 수 있습니다.
          </span>
        </span>
      </label>

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
