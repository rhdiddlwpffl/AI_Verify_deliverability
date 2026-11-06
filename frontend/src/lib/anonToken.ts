// 로그인 없이 '이 브라우저의 기록'을 구분하는 무작위 토큰.
// 서버에는 이 토큰의 해시만 저장되므로, 토큰을 아는 사람만 그 기록을 열 수 있다.
// 따라서 토큰을 로그, URL, 화면에 노출하지 않는다. (헤더로만 보낸다)

const STORAGE_KEY = 'answer-auditor.anon-token'
const TOKEN_PATTERN = /^[a-f0-9]{64}$/

let memoryToken: string | null = null
let persistent = true

function createToken(): string {
  const bytes = new Uint8Array(32) // 256비트
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

/** 저장된 토큰을 돌려주고, 없으면 새로 만든다. */
export function getAnonToken(): string {
  if (memoryToken) return memoryToken
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && TOKEN_PATTERN.test(stored)) {
      memoryToken = stored
      return stored
    }
    const created = createToken()
    localStorage.setItem(STORAGE_KEY, created)
    memoryToken = created
    return created
  } catch {
    // 브라우저가 저장소 사용을 막은 경우(시크릿 모드 등). 이 탭이 열려 있는 동안만 쓰는 임시 토큰.
    persistent = false
    memoryToken = memoryToken ?? createToken()
    return memoryToken
  }
}

/** 토큰이 브라우저에 남아 있는지. false이면 새로고침 후에는 이전 기록을 볼 수 없다. */
export function isTokenPersistent(): boolean {
  getAnonToken()
  return persistent
}
