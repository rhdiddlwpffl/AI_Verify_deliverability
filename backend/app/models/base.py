from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def uuid_pk() -> Any:
    """기본키: 파이썬에서 UUID를 만들어 넣는다. (순서를 추측할 수 없어 URL에 노출해도 안전)"""
    return Field(default_factory=uuid4, primary_key=True)


def created_at_field() -> Any:
    """생성 시각: 시간대(UTC) 포함. 파이썬 기본값과 DB 기본값(now())을 함께 둔다."""
    return Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


def jsonb_list_field() -> Any:
    """JSONB 배열 컬럼 (기본값 [])"""
    return Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    )


def jsonb_dict_field() -> Any:
    """JSONB 객체 컬럼 (기본값 {})"""
    return Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
