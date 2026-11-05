from datetime import datetime
from uuid import UUID

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, uuid_pk


class Verification(SQLModel, table=True):
    """주장 하나에 대한 검증 결과(화면 표시용 상태).

    '확정 판정'이 아니라 '검색된 출처 기준의 참고 정보'다.
    재검증하면 행이 추가되고, 화면에는 가장 최근 것을 보여 준다.
    """

    __tablename__ = "verifications"

    id: UUID = uuid_pk()
    claim_id: UUID = Field(foreign_key="claims.id", ondelete="CASCADE", index=True)
    status: str = Field(nullable=False)
    confidence: str | None = Field(default=None)
    rationale: str | None = Field(default=None, sa_type=Text)
    model: str | None = Field(default=None)
    created_at: datetime = created_at_field()
