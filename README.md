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
