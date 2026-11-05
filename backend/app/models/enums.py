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


class VulnerabilityFlag(StrEnum):
    """'취약점 신호'. 거짓이라는 뜻이 아니라, 다시 확인해 볼 만한 특징이다."""

    # 코드 규칙으로 찾는 신호
    ABSOLUTE_EXPRESSION = "absolute_expression"  # 항상, 반드시, 모든, 100% ...
    CONTAINS_NUMBER = "contains_number"  # 수치가 있음
    CONTAINS_YEAR = "contains_year"  # 연도가 있음
    VAGUE_ATTRIBUTION = "vague_attribution"  # '연구에 따르면' 처럼 출처 없는 인용
    QUOTATION = "quotation"  # 따옴표로 인용한 문구
    # Claude가 추가로 찾는 신호
    OVERGENERALIZATION = "overgeneralization"  # 일부 사례를 전체로 일반화
    UNVERIFIABLE_SPECIFICITY = "unverifiable_specificity"  # 확인하기 어려운 지나치게 구체적인 세부 내용
    CAUSAL_CLAIM = "causal_claim"  # 인과관계 단정
    POSSIBLY_OUTDATED = "possibly_outdated"  # 시간이 지나 바뀌었을 수 있는 내용


# Claude가 붙일 수 있는 신호 (나머지는 코드 규칙 전용)
LLM_FLAGS: tuple[VulnerabilityFlag, ...] = (
    VulnerabilityFlag.OVERGENERALIZATION,
    VulnerabilityFlag.UNVERIFIABLE_SPECIFICITY,
    VulnerabilityFlag.CAUSAL_CLAIM,
    VulnerabilityFlag.POSSIBLY_OUTDATED,
)


class Stance(StrEnum):
    """검색된 출처가 주장에 대해 취하는 입장. 참/거짓 판정이 아니다."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class SearchStatus(StrEnum):
    """한 주장에 대한 검색 결과 상태. '찾지 못함'과 '검색 실패'는 의미가 다르므로 구분한다."""

    NOT_SEARCHED = "not_searched"  # 확인 대상이 아니라서 검색하지 않음
    FOUND = "found"  # 관련 문서를 찾음 (주장을 뒷받침하는지는 별개)
    NONE = "none"  # 검색은 정상이었지만 문서를 찾지 못함
    FAILED = "failed"  # 검색 자체가 실패함 (한도 초과, 연결 실패, 시간 초과 등)
    SKIPPED = "skipped"  # 한 번에 검증하는 문장 수 제한 때문에 검색하지 않음


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
