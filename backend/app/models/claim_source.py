from uuid import UUID

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.models.enums import Stance


class ClaimSource(SQLModel, table=True):
    """주장과 출처의 연결. '이 출처의 이 부분이 이 주장에 대해 이런 입장'이라는 근거 한 건."""

    __tablename__ = "claim_sources"

    # 두 컬럼을 합쳐 기본키로 쓴다 (같은 주장-출처 쌍은 한 번만).
    claim_id: UUID = Field(foreign_key="claims.id", ondelete="CASCADE", primary_key=True)
    source_id: UUID = Field(foreign_key="sources.id", primary_key=True, index=True)
    snippet: str | None = Field(default=None, sa_type=Text)  # 검색 결과 발췌문
    relevance_score: float | None = Field(default=None)
    stance: str = Field(default=Stance.NEUTRAL.value, nullable=False)
    # 모델이 근거로 인용한 문장. quote_verified는 그 문장이 발췌문에 실제로 있는지 백엔드가 확인한 결과.
    quoted_text: str | None = Field(default=None, sa_type=Text)
    quote_verified: bool = Field(default=False, nullable=False)
