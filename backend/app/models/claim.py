from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_list_field, uuid_pk


class Claim(SQLModel, table=True):
    """분석 대상 답변에서 분리한 문장 하나 (사실 확인이 필요한지 여부 포함)."""

    __tablename__ = "claims"
    __table_args__ = (
        # 한 분석 안에서 문장 순번은 겹치지 않는다.
        UniqueConstraint("analysis_id", "idx", name="uq_claims_analysis_idx"),
    )

    id: UUID = uuid_pk()
    analysis_id: UUID = Field(foreign_key="analyses.id", ondelete="CASCADE", index=True)
    idx: int = Field(nullable=False)  # 문장 순서 (0부터)
    sentence_text: str = Field(sa_type=Text, nullable=False)
    # 원문(input_text)에서의 위치. 화면에서 하이라이트할 때 쓴다.
    start_offset: int = Field(nullable=False)
    end_offset: int = Field(nullable=False)
    claim_type: str = Field(nullable=False)
    reason: str | None = Field(default=None, sa_type=Text)  # AI가 적은 분류 이유
    # 위키백과 검색에 쓴 짧은 검색어. 확인 대상이 아닌 문장(검색하지 않음)은 비어 있다.
    search_query: str | None = Field(default=None, sa_type=Text)
    # 검색 결과 상태: not_searched | found | none | failed | skipped. ('찾지 못함'과 '검색 실패'를 구분해 저장)
    search_status: str = Field(
        default="not_searched", nullable=False, sa_column_kwargs={"server_default": "not_searched"}
    )
    search_error: str | None = Field(default=None)  # failed일 때 이유 코드
    check_worthy: bool = Field(default=False, nullable=False)
    # 취약점 신호 목록. 예: ["absolute_expression", "number_without_source"]
    vulnerability_flags: list[str] = jsonb_list_field()
    created_at: datetime = created_at_field()
