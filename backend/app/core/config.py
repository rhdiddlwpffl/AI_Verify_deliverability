from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수(.env)에서 읽어오는 설정 모음.

    값이 없으면 아래 기본값을 쓰고, .env 또는 실제 환경변수가 있으면 그 값이 우선합니다.
    """

    # local | production
    app_env: str = "local"
    # 쉼표로 구분된 프론트엔드 주소 목록 (CORS 허용 대상)
    cors_origins: str = "http://localhost:5173"

    # PostgreSQL 연결 문자열 (Supabase 대시보드에서 복사해 .env에 넣는다)
    database_url: str = ""

    # Claude API 키. SDK는 .env를 읽지 않으므로 이 설정값을 클라이언트에 직접 넘긴다.
    anthropic_api_key: str = ""
    # 문장 분류에 쓰는 모델과 추론 강도. 분류는 단순 작업이라 강도를 낮게 시작한다.
    extract_model: str = "claude-sonnet-5-5"
    extract_effort: str = "low"  # low | medium | high | xhigh | max
    # 위키백과 API 요청에 붙는 User-Agent. 위키미디어는 '설명이 담긴 User-Agent'를 요구하고,
    # 없으면 IP가 차단될 수 있다. 배포 전에 연락처(URL 또는 이메일)를 넣어야 한다.
    search_user_agent: str = "AnswerAuditor/0.1 (local development)"
    # 주장 하나당 가져올 검색 결과 수와, 결과마다 가져올 본문(도입부) 글자 수
    search_results_per_claim: int = 3
    search_extract_chars: int = 400
    # 근거 비교(발췌문이 주장을 뒷받침하는지) 호출의 모델/추론 강도. 분류보다 어려운 작업이라 강도를 높인다.
    judge_model: str = "claude-sonnet-5-5"
    judge_effort: str = "medium"  # low | medium | high | xhigh | max
    # 비교 호출 한 번에 담을 문장 수 / 동시에 보낼 비교 호출 수.
    # 나눠서 보내면 한 번의 실패가 전체로 번지지 않고 응답도 빨라진다.
    judge_chunk_size: int = 8
    judge_concurrency: int = 2
    # 한 번의 분석에서 검색할 최대 문장 수 / 동시에 보낼 검색 수 / 검색 단계 전체 제한 시간(초)
    max_verify_claims: int = 20
    search_concurrency: int = 3
    search_phase_timeout: float = 30.0
    # 입력 글자 수 상한 (비용 폭주 방지)
    max_input_chars: int = 5000
    # 한 번에 분석할 수 있는 최대 문장 수 (비용 폭주 방지). 넘으면 자르지 않고 오류로 알린다.
    max_sentences: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        """SQLAlchemy가 psycopg(v3) 드라이버를 쓰도록 주소 앞부분을 맞춘다.

        Supabase는 'postgresql://...' 형태로 주는데, 이대로는 SQLAlchemy가
        다른 드라이버를 찾는다. 'postgresql+psycopg://...'로 바꿔 준다.
        """
        url = self.database_url.strip()
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


settings = Settings()
