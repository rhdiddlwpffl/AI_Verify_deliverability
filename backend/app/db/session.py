from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from app.core.config import settings


class DatabaseNotConfiguredError(RuntimeError):
    """DATABASE_URL이 비어 있을 때 발생한다."""


@lru_cache
def get_engine() -> Engine:
    """DB 연결 엔진을 처음 필요할 때 한 번만 만든다.

    import 시점이 아니라 '처음 쓸 때' 만드는 이유: DATABASE_URL이 없어도
    서버가 켜지고 /health 같은 DB 없는 기능은 동작하게 하려는 것이다.
    """
    url = settings.sqlalchemy_database_url
    if not url:
        raise DatabaseNotConfiguredError("DATABASE_URL이 설정되지 않았습니다.")
    return create_engine(
        url,
        pool_pre_ping=True,  # 끊어진 연결을 쓰기 전에 감지해서 새로 연결
        pool_size=5,  # 무료 DB의 연결 수 제한을 고려해 작게 유지
        max_overflow=2,
        connect_args={"connect_timeout": 5},  # DB가 응답 없을 때 5초 후 포기
    )


def get_session() -> Iterator[Session]:
    """FastAPI 의존성: 요청마다 DB 세션을 열고, 끝나면 닫는다."""
    with Session(get_engine()) as session:
        yield session
