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
