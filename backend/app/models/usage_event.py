from datetime import datetime
from uuid import UUID

from sqlalchemy import Index
from sqlmodel import SQLModel

from app.models.base import created_at_field, uuid_pk


class UsageEvent(SQLModel, table=True):
    """분석 요청 1건의 사용 기록. '24시간 사용 횟수' 제한을 서버가 재시작해도 유지하기 위한 것이다.

    IP 원본은 저장하지 않고, 비밀 값(salt)을 섞은 해시만 저장한다.
    이틀이 지난 기록은 새 요청이 들어올 때 함께 지운다.
    """

    __tablename__ = "usage_events"
    __table_args__ = (
        Index("ix_usage_events_created_at", "created_at"),  # 전체 24시간 횟수 조회
        Index("ix_usage_events_ip_created", "ip_hash", "created_at"),  # IP별 24시간 횟수 조회
    )

    id: UUID = uuid_pk()
    ip_hash: str
    created_at: datetime = created_at_field()
