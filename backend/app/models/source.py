from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, Text, text
from sqlmodel import Field, SQLModel

from app.models.base import utcnow, uuid_pk


class Source(SQLModel, table=True):
    """검색으로 찾은 출처 웹페이지. 같은 URL은 한 번만 저장하고 여러 주장이 공유한다."""

    __tablename__ = "sources"

    id: UUID = uuid_pk()
    url: str = Field(sa_type=Text, nullable=False, unique=True)
    title: str | None = Field(default=None, sa_type=Text)
    domain: str | None = Field(default=None, index=True)
    fetched_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
