from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SALT = "dev-only-salt-change-me"


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

    # ---- 호출 횟수 제한 (분석 1회에 Claude 비용이 들기 때문에 남용을 막는다) ----
    rate_limit_ip_per_minute: int = 3  # IP당 분석 요청 (서버 메모리)
    rate_limit_ip_per_day: int = 20  # IP당 24시간 분석 요청 (DB에 기록)
    rate_limit_global_per_day: int = 60  # 전체 24시간 분석 요청 = 하루 비용의 상한 (DB에 기록)
    rate_limit_history_per_minute: int = 60  # IP당 기록 조회/삭제 요청 (가볍게)
    max_concurrent_analyses: int = 3  # 동시에 실행하는 분석 수. 넘으면 503
    # 배포 환경에서 앞단 프록시(Render 등)가 몇 개인지. 0이면 연결 상대의 주소를 그대로 쓴다.
    # 1 이상이면 X-Forwarded-For의 '오른쪽에서 N번째'를 클라이언트 주소로 본다. 맨 왼쪽 값은
    # 클라이언트가 마음대로 쓸 수 있어서 믿지 않는다. (배포 때 가짜 헤더로 확인할 것)
    trusted_proxy_count: int = 0
    # IP를 해시할 때 섞는 비밀 값. IPv4는 경우의 수가 적어서 salt 없이 해시하면 되돌릴 수 있다.
    rate_limit_salt: str = _DEV_SALT

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
    # 저장된 분석 기록의 보관 일수. 저장할 때 이보다 오래된 기록을 함께 지운다. (0이면 자동 삭제 안 함)
    retention_days: int = 30
    # '내 기록' 목록에서 한 번에 가져올 최대 개수
    history_page_size: int = 50
    # 한 번의 분석에서 검색할 최대 문장 수 / 동시에 보낼 검색 수 / 검색 단계 전체 제한 시간(초)
    max_verify_claims: int = 20
    search_concurrency: int = 3
    search_phase_timeout: float = 30.0
    # 입력 글자 수 상한 (비용 폭주 방지)
    max_input_chars: int = 5000
    # 한 번에 분석할 수 있는 최대 문장 수 (비용 폭주 방지). 넘으면 자르지 않고 오류로 알린다.
    max_sentences: int = 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def _require_real_salt_in_production(self) -> "Settings":
        # 개발용 기본 salt로 배포하면 저장된 IP 해시가 되돌려질 수 있다. 시작 단계에서 막는다.
        if self.app_env == "production" and (self.rate_limit_salt == _DEV_SALT or len(self.rate_limit_salt) < 16):
            raise ValueError("production에서는 RATE_LIMIT_SALT를 16자 이상의 비밀 값으로 설정해야 합니다.")
        return self

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
