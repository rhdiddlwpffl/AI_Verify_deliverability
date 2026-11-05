from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Text
from sqlmodel import Field, SQLModel

from app.models.base import created_at_field, jsonb_dict_field, uuid_pk
from app.models.enums import AnalysisStatus


class Analysis(SQLModel, table=True):
    """사용자가 붙여 넣은 AI 답변 하나에 대한 분석 기록."""

    __tablename__ = "analyses"

    id: UUID = uuid_pk()
    # 비로그인 사용자도 쓸 수 있어 null 허용. 사용자를 지우면 이 기록도 함께 지운다.
    user_id: UUID | None = Field(
        default=None, foreign_key="users.id", ondelete="CASCADE", index=True
    )
    # 비로그인 사용자의 기록을 구분하는 토큰. 나중에 가입하면 user_id에 연결한다.
    anon_token: str | None = Field(default=None, index=True)
    input_text: str = Field(sa_type=Text, nullable=False)
    status: str = Field(default=AnalysisStatus.PENDING.value, nullable=False)
    # 사용한 모델/설정 등 부가 정보
    model_info: dict[str, Any] = jsonb_dict_field()
    created_at: datetime = created_at_field()
