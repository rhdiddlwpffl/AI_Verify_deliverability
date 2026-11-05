"""허용하는 값 목록.

DB에는 일반 문자열로 저장하고(ENUM 타입 미사용), 허용 값 검사는 코드에서 한다.
값을 추가/변경할 때 DB 마이그레이션이 필요 없게 하려는 선택이다.
"""

from enum import StrEnum


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class ClaimType(StrEnum):
    FACTUAL = "factual"
    NUMERIC = "numeric"
    QUOTE = "quote"
    OPINION = "opinion"
    OTHER = "other"


class Stance(StrEnum):
    """검색된 출처가 주장에 대해 취하는 입장. 참/거짓 판정이 아니다."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class VerificationStatus(StrEnum):
    """화면에 보여 줄 검증 상태. '확정 판정'이 아니라 '검색된 출처 기준'의 표시다."""

    NOT_CHECKABLE = "not_checkable"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    INSUFFICIENT = "insufficient"
    SEARCH_FAILED = "search_failed"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
