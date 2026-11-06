# Answer Auditor (AI 답변 검증기)

AI 답변을 문장별로 나눠, 사실 확인이 필요한 주장과 근거가 부족한 부분을 표시하는 도구입니다.

> **주의**: 이 도구의 결과는 "검색된 출처 기준의 참고 정보"입니다. 근거가 있다고 해서 반드시 참인 것은 아니며, 최종 판단은 원문 출처를 직접 확인해서 하세요.

## 구조
- `frontend/` : React + Vite + TypeScript (배포: Vercel)
- `backend/` : Python + FastAPI (배포: Render)
- DB : PostgreSQL (Supabase)

## 설정 파일
비밀값(API 키, DB 주소)은 `.env` 파일에만 넣고 GitHub에 올리지 않습니다.
각 폴더의 `.env.example`을 복사해서 `.env`를 만드세요.

## 진행 상황
- [x] 1단계: 저장소와 뼈대
- [x] 2단계: 백엔드 Hello (FastAPI, `/health`, CORS)
- [x] 3단계: 프론트 Hello (Vite + React + TS, `/health` 호출)
- [x] 4단계: DB 연결 (Supabase PostgreSQL, `/health/db`)
- [x] 5단계: 데이터 모델(SQLModel 6개 테이블) + Alembic 마이그레이션
- [x] 6단계: 주장 추출 (문장 분리, Claude 분류, `POST /analyses`, 하이라이트 화면)
- [x] 7단계: 검색 근거 (위키백과 API: 검색어 생성, 주장별 병렬 검색, 화면에 근거 후보 표시)
- [x] 8단계: 근거 비교와 상태 표시 (인용문 글자 단위 검증, 코드가 상태 계산, "검색된 출처 기준" 표현)
- [x] 9단계: 분석 기록 저장/조회/삭제 (익명 토큰 해시, 기본 저장 꺼짐, 30일 자동 삭제)
- [x] 10단계: 호출 횟수 제한, 위키백과 한도 대응, 샘플 답변, 접근성 점검, 모델 평가
- [x] 11단계: 테스트 정리 (pytest, Vitest, 계약 테스트, 문구 가드, 린트, CI)
- [~] 12단계: 배포 (운영 Supabase, Render, Vercel 배포 완료. 운영 환경에서 IP별 분당 호출 제한이 의도대로 걸리는지는 **아직 확인되지 않음**, 아래 '배포' 참고)

## 배포
| 구성 | 위치 | 비고 |
|---|---|---|
| 프론트엔드 | Vercel, 루트 폴더 `frontend`, 환경변수 `VITE_API_BASE_URL`(끝에 `/` 없이) | https://ai-verify-deliverability.vercel.app |
| 백엔드 | Render 무료 플랜, 설정은 `render.yaml`(Blueprint) | https://answer-auditor-api.onrender.com (`/health`, `/docs`) |
| DB | Supabase 운영 프로젝트(개발용과 분리) | 마이그레이션은 `alembic upgrade head`로 직접 적용 |

- 비밀값(`DATABASE_URL`, `ANTHROPIC_API_KEY`)은 Render 대시보드에만 입력합니다. `RATE_LIMIT_SALT`는 Render가 생성합니다. `CORS_ORIGINS`에는 Vercel 주소를 넣습니다.
- **운영 DB 연결은 Transaction pooler(포트 6543)를 씁니다.** Session pooler(5432)는 동시 클라이언트 한도가 작아, 배포 후 가벼운 동시 요청에서도 `max clients reached in session mode`(503)가 났습니다(실측). 포트가 6543이면 코드가 psycopg의 준비된 쿼리를 자동으로 끕니다. 마이그레이션은 5432로 실행합니다.
- 시작 명령에 `--no-proxy-headers`가 들어 있습니다(없으면 `X-Forwarded-For`로 호출 제한을 우회할 수 있음).
- **확인되지 않은 것**: 운영에서 `TRUSTED_PROXY_COUNT`가 올바른지(Render는 Cloudflare 뒤에 있어 값을 실측해야 함). 기록 조회 100회를 보내도 모두 통과해 IP별 분당 제한이 운영에서 제대로 걸리지 않을 수 있습니다. 분석의 24시간 한도는 DB 기반이며 이 점검과는 별개입니다. Anthropic 콘솔의 월 사용 한도는 직접 설정해야 합니다.
- 무료 플랜은 유휴 후 첫 요청이 느릴 수 있습니다.

## API: `POST /analyses`
AI 답변을 문장별로 분석합니다. (현재는 DB에 저장하지 않음)
```
요청:  {"text": "분석할 AI 답변"}                       # 최대 5,000자
응답:  {"claims": [{"idx", "text", "start", "end",       # start/end = JavaScript text.slice(start, end) 기준(UTF-16)
                    "claim_type", "check_worthy", "flags", "reason"}],
        "sentence_count", "check_worthy_count", "model"}
오류:  {"error": {"code": "...", "message": "사용자에게 보여 줄 한국어 문장"}}
```
- `flags`(취약점 신호)는 "다시 확인해 볼 만한 특징"이지 거짓 판정이 아닙니다. `check_worthy=false`인 문장에는 비어 있습니다.
- 검색 필드: `search_status`(`found` 문서를 찾음 / `none` 정상 검색했지만 없음 / `failed` 검색 자체가 실패 / `skipped` 개수 제한으로 건너뜀 / `not_searched` 확인 대상 아님), `search_query`, `search_error`, `sources`(제목, 링크, 도입부 본문). **`none`과 `failed`는 다른 상황**이며, 검색된 문서가 주장을 뒷받침하는지는 아직 판단하지 않습니다(8단계).
- 검증 필드: `verification_status`(`supported` 검색된 출처에서 뒷받침하는 내용 발견 / `contradicted` 상충하는 내용 발견 / `mixed` 엇갈림 / `insufficient` 근거 부족 / `search_failed` 검색 실패 / `unverified` 비교하지 못함 / `not_checkable` 검증 대상 아님), `verification_confidence`(근거 강도), `verification_rationale`, 출처별 `stance`/`quote`/`downgraded`. **확정 판정이 아니라 "검색된 출처 기준"의 참고 정보입니다.**
  - 최종 상태는 AI가 아니라 코드가 계산합니다. AI는 출처별 stance와 인용문만 돌려주고, 코드가 인용문이 발췌문에 실제로 있는지 글자 단위로 확인합니다. 없거나, 발췌문이 주장과 다른 대상/시점을 다루면(`same_scope=false`) 그 근거는 `neutral`로 낮춥니다.
  - 한계: 인용문이 발췌문에 있다는 것과 그 인용이 주장을 정말 뒷받침한다는 것은 다릅니다. 근거는 위키백과 문서의 앞부분(기본 400자)뿐이라 문서 뒷부분의 내용은 `insufficient`로 나옵니다.
- **기록 저장/조회/삭제** (로그인 없이 브라우저의 익명 토큰으로 구분)
  - 요청 헤더 `X-Anon-Token`: 브라우저가 만든 무작위 토큰(64자 16진수). 서버에는 **SHA-256 해시만** 저장하고 원본은 저장하지 않습니다.
  - `POST /analyses`에 `{"save": true}` + 토큰이 있을 때만 입력 원문과 결과를 저장합니다. **기본은 저장 안 함**입니다. 응답의 `save_status`는 `not_requested | saved | failed | no_token`이고, 저장이 실패해도 분석 결과는 정상으로 돌려줍니다.
  - `GET /analyses`(내 기록 목록), `GET /analyses/{id}`(분석 직후 응답과 같은 형식의 `result` 포함), `DELETE /analyses/{id}`, `DELETE /analyses`(내 기록 전체). 남의 기록이나 없는 기록은 모두 404입니다.
  - `RETENTION_DAYS`(기본 30일)가 지난 기록은 저장할 때 함께 정리됩니다(별도 스케줄러 없음). 삭제하면 하위 데이터가 함께 지워지고, 아무도 참조하지 않는 출처도 정리됩니다.
  - 한계: 브라우저 데이터를 지우거나 다른 기기를 쓰면 기록이 보이지 않습니다. 로그인 기능을 붙이면 토큰의 기록을 계정으로 옮깁니다.
  - 개인정보: 입력한 글은 분석을 위해 Anthropic(AI)으로, 검색어(핵심어)는 위키백과로 전송됩니다. 화면에도 안내합니다.
- **호출 횟수 제한** (분석 1회에 Claude 비용이 든다. 실측 5문장 약 $0.03, 최대 약 $0.11)
  - 기본값: IP당 분당 3회, IP당 24시간 20회, 전체 24시간 60회, 동시 분석 3개. 기록 조회/삭제는 IP당 분당 60회. 모두 `.env`에서 바꿉니다.
  - 한도를 넘으면 429(+`Retry-After`)와 구분된 메시지: `rate_limited`(분당), `daily_limit_reached`(내 24시간), `service_daily_limit`(서비스 전체). 동시 실행이 가득 차면 503 `busy`.
  - **24시간 한도는 DB(`usage_events`)에 기록**합니다. 서버가 재시작하거나 절전에서 깨어나도 유지되고, DB를 쓸 수 없으면 메모리 카운터로 계속 제한합니다. IP는 salt를 섞은 HMAC 해시로만 저장하며 이틀 지난 기록은 지웁니다.
  - 잘못된 입력(빈 글 등)은 횟수를 소모하지 않습니다.
  - `APP_ENV=production`에서는 `RATE_LIMIT_SALT`(16자 이상)를 설정하지 않으면 서버가 시작되지 않습니다. 배포 환경은 `TRUSTED_PROXY_COUNT`도 설정하세요(Render는 1로 시작해 확인).
  - **운영에서는 서버를 반드시 `uvicorn app.main:app --no-proxy-headers ...`로 실행하세요.** 실측 결과, 이 옵션 없이 `TRUSTED_PROXY_COUNT=0`이면 uvicorn이 `X-Forwarded-For`를 믿고 주소를 바꿔서 같은 사람이 헤더만 바꿔 한도를 우회할 수 있었습니다.
  - 한계: IP를 공유하는 사용자(학교, 회사)는 함께 제한됩니다. 전체 한도는 누군가 일부러 채워서 다른 사용자의 사용을 막을 수 있습니다(비용 상한이 목적). **Anthropic 콘솔에서 월 사용 한도도 직접 설정**해 두세요.
- **위키백과 요청 한도**(2026-11 실측): 익명 요청은 한 번에 약 10개까지 허용되고 지속 속도는 약 0.4개/초입니다. 넘으면 429와 `Retry-After` 21~47초가 오며, **걸린 채 계속 요청하면 대기 시간이 늘어납니다.** 서버의 모든 사용자가 같은 IP를 공유하므로 한도도 함께 나눠 씁니다.
  - 대응: 요청 속도 조절(버스트 8, 초당 0.3개), 429 쿨다운(짧으면 기다리고 길면 요청 없이 즉시 실패), 검색 결과 1시간 캐시, **한 번에 검증하는 문장을 10개로 제한하고 취약점 신호가 많은 문장부터 선택**.
  - 개선 전(20문장, 동시성 3)에는 20개 중 6~14개가 "검색 실패"였고, 개선 후(10문장)에는 3회 모두 10/10 성공했습니다. 다만 **연달아 분석하면 28초**까지 걸립니다.
  - 한계: 연락처가 있는 User-Agent로 배포하면 한도가 달라질 수 있어 **배포 후 다시 측정**해야 합니다.
- 근거 후보는 위키백과(CC BY-SA 4.0)입니다. 배포 전에 `SEARCH_USER_AGENT`에 연락처(저장소 URL 또는 이메일)를 넣어야 합니다. 위키미디어가 설명 있는 User-Agent를 요구합니다.
- 오류 코드: `empty_input`, `input_too_long`, `no_sentences`, `too_many_sentences`, `invalid_request`, `invalid_json`, `analysis_refused`, `analysis_failed`, `llm_not_configured`, `llm_auth_error`, `llm_rate_limited`, `llm_timeout`, `llm_unavailable`, `llm_request_error`, `llm_error`
- 수동 시험: `backend/scripts/try_classify.py`(실제 API 호출, 비용 발생), `backend/scripts/check_offsets.py`

## DB 마이그레이션 (backend 폴더에서)
```
.venv\Scripts\python -m alembic upgrade head                           # 최신 구조로 적용
.venv\Scripts\python -m alembic revision --autogenerate -m "설명"       # 모델 변경분으로 새 마이그레이션 생성
.venv\Scripts\python -m alembic current                                # 현재 DB 버전 확인
```
- 자동 생성된 파일은 **적용 전에 반드시 열어서 확인**하세요. 특히 `drop_table`, `drop_column`이 의도한 것인지 봅니다.
- `alembic.ini`는 한글 등 비ASCII 문자를 넣지 마세요(Windows 기본 인코딩으로 읽음).
- 새 마이그레이션에서 테이블을 만들면 RLS를 켜는 구문도 함께 넣습니다(첫 마이그레이션 참고).

## 요구 사항
- Node.js **22.12 이상** (Vite 8 요구사항), Python 3.12 이상

## 프론트엔드 실행
```
cd frontend
npm install                           # 최초 1회
npm run dev                           # http://localhost:5173
```
- 로컬에서는 `VITE_API_BASE_URL`이 없으면 `http://localhost:8000`을 사용합니다. 바꾸려면 `.env.example`을 `.env.local`로 복사하세요.

## 백엔드 실행 (Windows)
```
cd backend
py -m venv .venv                      # 최초 1회
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```
- 상태 확인: http://localhost:8000/health
- API 문서: http://localhost:8000/docs

## 테스트
```
# 백엔드 (backend 폴더에서)
.venv\Scripts\python -m pip install -r requirements-dev.txt        # 최초 1회 (테스트 도구는 운영 의존성과 분리)
.venv\Scripts\python -m pytest                                      # 전체. DATABASE_URL이 있으면 DB 통합 테스트도 실행
.venv\Scripts\python -m pytest -m "not db"                          # DB 없이 (CI와 같은 조건)
.venv\Scripts\python -m pytest -m db                                # DB 통합 테스트만
.venv\Scripts\python -m pytest --cov=app --cov-report=term-missing  # 커버리지
.venv\Scripts\python -m ruff check .                                # 린트

# 프론트엔드 (frontend 폴더에서)
npm run check                          # 린트 + 테스트 + 빌드를 한 번에 (올리기 전에 이것 하나)
npm test                               # 테스트만
node scripts/check-contrast.mjs        # 색 대비(WCAG) 점검
```
- 현재: 백엔드 182개(DB 통합 17개 포함, 커버리지 98%는 11단계 시점 측정), 프론트 90개. DB 없이 돌리면 165개 통과 + 17개 **건너뜀**(1~2초).
- **안전장치**: 테스트가 실수로 실제 Claude나 위키백과를 호출하면 실패합니다(`tests/conftest.py`). DB 통합 테스트는 트랜잭션 안에서 실행하고 롤백해서 DB에 데이터를 남기지 않습니다. DB가 없으면 조용히 통과하지 않고 "건너뜀"으로 표시됩니다.
- **계약 테스트**(`frontend/src/contract.test.ts`): 백엔드 파이썬 소스를 직접 읽어서, 백엔드가 내보내는 상태·신호·유형·오류 코드마다 프론트에 한국어 이름과 처리가 있는지, 응답 필드가 타입 정의와 같은지, 두 곳에 적은 값(보관 기간 30일, 입력 상한 5,000자)이 같은지 확인합니다. 한쪽만 고치는 실수를 잡습니다.
- **문구 가드**(`labels.test.ts`, `components.test.tsx`): 상태 이름에 "참/거짓/정확/틀림" 같은 판정 글자가 들어가면, 화면 어디에서든 확정 문장이 나오면, `https`가 아닌 링크가 만들어지면, 저장 체크박스 기본값이 바뀌면 실패합니다. 이 서비스의 핵심 원칙(검색된 출처 기준의 참고 정보)을 코드로 고정한 것입니다.
- 비용이 드는 점검은 `pytest`에 **포함하지 않았습니다**: `backend/scripts/e2e_*.py`(실제 서버 end-to-end, 분석 1~2회), `backend/scripts/eval/`(모델 평가, 아래).
- **테스트가 보증하지 않는 것**: (1) 실제 네트워크를 타는 함수(`searcher._urllib_fetch`)는 오프라인 테스트로 확인할 수 없어서 실제 위키백과로만 검증됩니다(과거에 httpx2가 403을 받았던 문제도 오프라인 테스트는 통과했습니다). (2) 화면은 브라우저 자동화 없이 문자열 렌더링으로만 확인하므로 레이아웃, 모양, 스크린 리더 동작은 직접 봐야 합니다. (3) 커버리지가 높아도 테스트가 맞는 것을 검사한다는 보증은 아닙니다. 그래서 핵심 테스트는 코드를 일부러 망가뜨려서 실제로 실패하는지 확인했습니다(변이 시험, 일회성 점검).
- CI(`.github/workflows/ci.yml`): GitHub에 올리면 린트, 테스트, 마이그레이션 체인 검증, 빌드, 색 대비를 자동으로 돌립니다. **GitHub 위에서 직접 실행해 본 적은 없습니다.**
- 줄바꿈은 `.gitattributes`로 LF에 고정합니다. (Windows에서 새로 받으면 CRLF가 되어, 소스를 줄 단위로 읽는 테스트가 깨진 적이 있습니다)

## 모델 평가 (Haiku 5.5 vs Sonnet 5.5)
`backend/scripts/eval/`에 평가 세트와 실행 스크립트가 있습니다. 기본은 예상 비용만 출력하고 `--yes`를 줘야 Claude를 호출합니다.
```
.venv\Scripts\python -X utf8 scripts\eval\fetch_evidence.py                      # 위키백과 발췌문을 고정(무료)
.venv\Scripts\python -X utf8 scripts\eval\run_eval.py --stage all --runs 3          # 예상 비용 출력
.venv\Scripts\python -X utf8 scripts\eval\run_eval.py --stage all --runs 3 --yes    # 실제 실행
```
- 평가 세트: 확인 대상 31문장(도입부로 확인되는 것, 같은 항목의 값이 틀린 것, 확인 못 하는 것, 시점이 다른 통계 함정, 숫자 한 끗 차이, 부정문 등)과 확인 대상이 아닌 7문장(의견, 제목, 인사, 질문, 예측, 지시문). **정답은 발췌문을 보고 작성자가 직접 정한 값**이라 주관이 섞여 있고, 문장 수가 적어(정확도 대상 29개) 작은 차이는 통계적으로 의미가 없습니다.
- **분류**(확인 대상 구분, 검색어): 두 모델이 동일했습니다. 확인 대상 재현율 93/93, 아닌 문장 특이도 21/21(지시문 포함), 검색어로 정답 문서를 찾은 비율 87/90. Haiku가 약 19배 저렴하고 더 빨랐습니다.
- **근거 비교**(같은 발췌문, 2회): Sonnet 58/58, Haiku(medium) 56/58, Haiku(low) 55/58. 없는 반박/근거를 만든 건수는 Sonnet과 Haiku(medium) 모두 0이었고, **Haiku(low)는 회차마다 결과가 달라지고(3/29) 핵심어만 겹치는 문장을 반박으로 착각한 경우가 1건** 있었습니다. Haiku(medium)는 틀린 주장 1건(연도만 다른 반박)을 놓쳤고, 출력이 길어 Sonnet보다 느렸습니다. 비용은 Haiku가 약 13배 저렴합니다.
- 결론(2026-11, 사용자 결정): **분류는 Haiku 5.5, 근거 비교는 Sonnet 5.5(effort medium)**를 기본값으로 씁니다. 평가 세트가 작아 **확정은 아니며**, `EXTRACT_MODEL`, `JUDGE_MODEL`, `JUDGE_EFFORT`로 언제든 바꿀 수 있습니다. 분석 1회 최대 비용은 약 $0.05(검증 10문장 기준 추정)입니다.
