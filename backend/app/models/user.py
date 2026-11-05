from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, uuid_pk


class User(SQLModel, table=True):
    """회원. 지금은 로그인 기능이 없어 비어 있지만, 확장을 위해 처음부터 만든다."""

    __tablename__ = "users"

    id: UUID = uuid_pk()
    # unique + null 허용: PostgreSQL은 NULL끼리는 중복으로 보지 않는다.
    email: str | None = Field(default=None, unique=True, index=True)
    password_hash: str | None = Field(default=None)
    created_at: datetime = created_at_field()
