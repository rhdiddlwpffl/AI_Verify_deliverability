import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import DatabaseNotConfiguredError, get_engine

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    """서버가 살아 있는지 확인하는 용도. 배포 후 모니터링에도 쓰입니다."""
    return {"status": "ok", "env": settings.app_env}


@router.get("/health/db")
def health_db() -> dict:
    """DB에 실제로 연결되는지 확인한다. (SELECT 1 한 번)"""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except DatabaseNotConfiguredError:
        raise AppError(503, "db_not_configured", "DATABASE_URL이 설정되지 않았습니다.")
    except Exception as exc:
        # 원인(예외 종류)은 서버 로그에만 남긴다.
        # 응답에는 넣지 않는다: 예외 메시지에 접속 주소나 계정 정보가 섞일 수 있다.
        logger.error("DB 연결 실패: %s", type(exc).__name__)
        raise AppError(503, "db_unavailable", "DB에 연결할 수 없습니다.")
    return {"status": "ok", "database": "connected"}
