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
