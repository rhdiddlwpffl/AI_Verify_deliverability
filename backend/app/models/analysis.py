from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index, Text
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_dict_field, uuid_pk
from app.models.enums import AnalysisStatus


class Analysis(SQLModel, table=True):
    """사용자가 붙여 넣은 AI 답변 하나에 대한 분석 기록."""

    __tablename__ = "analyses"
    # '내 기록 목록'(토큰별 최신순) 조회용 인덱스
    __table_args__ = (Index("ix_analyses_anon_created", "anon_token_hash", "created_at"),)

    id: UUID = uuid_pk()
    # 비로그인 사용자도 쓸 수 있어 null 허용. 사용자를 지우면 이 기록도 함께 지운다.
    user_id: UUID | None = Field(
        default=None, foreign_key="users.id", ondelete="CASCADE", index=True
    )
    # 비로그인 사용자의 기록을 구분하는 토큰의 SHA-256 해시. (토큰 원본은 저장하지 않는다:
    # DB가 유출돼도 토큰으로 남의 기록을 열 수 없게 하기 위해서) 나중에 가입하면 user_id에 연결한다.
    anon_token_hash: str | None = Field(default=None)
    input_text: str = Field(sa_type=Text, nullable=False)
    status: str = Field(default=AnalysisStatus.PENDING.value, nullable=False)
    # 사용한 모델/설정 등 부가 정보
    model_info: dict[str, Any] = jsonb_dict_field()
    created_at: datetime = created_at_field()
