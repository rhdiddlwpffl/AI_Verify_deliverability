"""분석 파이프라인: 문장 분리 → Claude 분류. (7~8단계에서 검색/검증 단계가 여기에 추가된다.)

SDK/모델 예외를 사용자에게 보여 줄 AppError로 바꾸는 곳이기도 하다.
로그에는 오류 종류와 요청 ID만 남기고, 입력 원문은 남기지 않는다.
"""

import logging

import anthropic

from dataclasses import dataclass

from app.core.config import settings
from app.core.errors import AppError
from app.services.claim_extractor import (
    ClassificationError,
    ClassificationRefusedError,
    ClassificationResult,
    LLMNotConfiguredError,
    TooManySentencesError,
    classify_sentences,
)
from app.models.enums import SearchStatus, VerificationStatus
from app.services.claim_extractor import ClaimAnalysis, TokenUsage
from app.services.evidence import Evidence, gather_evidence
from app.services.searcher import get_provider
from app.services.sentence_splitter import split_sentences
from app.services.verifier import JudgeResult, SourceVerdict, judge_claims

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimVerification:
    """한 문장의 '검색된 출처 기준' 검증 결과. 사실 여부의 확정 판정이 아니다."""

    status: str  # VerificationStatus 값
    confidence: str | None = None  # 근거 강도(검증된 인용 수 기준). 사실 여부의 확실성이 아니다
    rationale: str | None = None
    error: str | None = None  # 비교 호출이 실패한 이유 (status가 unverified일 때)
    source_verdicts: list[SourceVerdict] | None = None  # 문서를 찾고 비교에 성공했을 때만


@dataclass
class AnalysisOutcome:
    classification: ClassificationResult
    evidence: dict[int, Evidence]  # 문장 번호(idx) → 검색 결과
    verification: dict[int, ClaimVerification]  # 문장 번호(idx) → 비교 결과
    judge_usage: TokenUsage  # 비교 호출의 토큰 사용량 (비용 확인용)


def _verification_for(claim: ClaimAnalysis, ev: Evidence, judged: JudgeResult) -> ClaimVerification:
    idx = claim.sentence.idx
    if not claim.check_worthy:
        return ClaimVerification(VerificationStatus.NOT_CHECKABLE.value)
    if ev.status == SearchStatus.SKIPPED.value:
        return ClaimVerification(VerificationStatus.UNVERIFIED.value, error="skipped")
    if ev.status == SearchStatus.FAILED.value:
        return ClaimVerification(VerificationStatus.SEARCH_FAILED.value, error=ev.error)
    if ev.status == SearchStatus.NONE.value:
        return ClaimVerification(VerificationStatus.INSUFFICIENT.value)  # 찾지 못함: 비교할 대상이 없다
    if idx in judged.judgments:
        j = judged.judgments[idx]
        return ClaimVerification(j.status, j.confidence, j.rationale or None, None, j.source_verdicts)
    return ClaimVerification(VerificationStatus.UNVERIFIED.value, error=judged.failed.get(idx, "judge_failed"))


def _llm_error(exc: Exception) -> AppError:
    """Anthropic SDK 예외 → 사용자용 오류. 응답에는 내부 정보를 싣지 않는다."""
    request_id = getattr(exc, "request_id", None)
    logger.error("Claude API 오류: %s (status=%s, request_id=%s)", type(exc).__name__, getattr(exc, "status_code", None), request_id)

    if isinstance(exc, anthropic.RateLimitError):
        return AppError(429, "llm_rate_limited", "요청이 많아 잠시 처리할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return AppError(502, "llm_auth_error", "AI 서비스 인증에 문제가 있습니다. 서버 설정을 확인해야 합니다.")
    if isinstance(exc, anthropic.APITimeoutError):
        return AppError(504, "llm_timeout", "AI 서비스 응답이 늦어지고 있습니다. 잠시 후 다시 시도해 주세요.")
    if isinstance(exc, anthropic.APIConnectionError):
        return AppError(502, "llm_unavailable", "AI 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    if isinstance(exc, anthropic.BadRequestError):
        # 크레딧 소진, 잘못된 파라미터 등. 원인은 서버 로그(요청 ID)로 확인한다.
        return AppError(502, "llm_request_error", "AI 서비스가 요청을 처리하지 못했습니다. 서버 설정(사용 한도 등)을 확인해야 합니다.")
    return AppError(502, "llm_error", "AI 서비스에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


def analyze_text(text: str) -> AnalysisOutcome:
    if not text.strip():
        raise AppError(422, "empty_input", "분석할 내용을 입력해 주세요.")

    sentences = split_sentences(text)
    if not sentences:
        raise AppError(422, "no_sentences", "분석할 문장을 찾지 못했습니다. 코드 블록이나 기호만 있는 입력은 분석하지 않습니다.")

    try:
        result = classify_sentences(sentences)
    except TooManySentencesError as exc:
        raise AppError(422, "too_many_sentences", str(exc)) from exc
    except ClassificationRefusedError as exc:
        raise AppError(422, "analysis_refused", "AI 서비스가 이 내용의 분석을 거부했습니다.") from exc
    except LLMNotConfiguredError as exc:
        logger.error("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        raise AppError(503, "llm_not_configured", "AI 분석 기능이 아직 설정되지 않았습니다.") from exc
    except ClassificationError as exc:
        logger.error("분류 실패: %s", exc)
        raise AppError(502, "analysis_failed", "AI 응답을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
    except anthropic.AnthropicError as exc:
        raise _llm_error(exc) from exc

    # 비용 추적용 로그. 입력 원문은 남기지 않는다.
    logger.info(
        "분석 완료: 문장 %d개, 확인 필요 %d개, 토큰 입력 %d / 출력 %d, 모델 %s",
        len(result.claims),
        sum(c.check_worthy for c in result.claims),
        result.usage.input_tokens,
        result.usage.output_tokens,
        result.model,
    )

    # 검색은 일부가 실패해도 전체를 실패시키지 않는다. (실패는 문장별로 기록되어 화면에 표시된다)
    evidence = gather_evidence(
        result.claims,
        get_provider(),
        max_claims=settings.max_verify_claims,
        concurrency=settings.search_concurrency,
        timeout=settings.search_phase_timeout,
    )

    # 찾은 문서가 있는 문장만 AI로 비교한다. 비교가 일부 실패해도 나머지는 살린다.
    items = [
        (c.sentence.idx, c.sentence.text, evidence[c.sentence.idx].results)
        for c in result.claims
        if evidence[c.sentence.idx].status == SearchStatus.FOUND.value
    ]
    try:
        judged = judge_claims(items)
    except ValueError as exc:  # 설정 오류(예: JUDGE_EFFORT 값이 올바르지 않음)
        logger.error("비교 설정 오류: %s", exc)
        judged = JudgeResult(failed={idx: "judge_failed" for idx, _, _ in items})
    logger.info(
        "비교 완료: %d문장 중 성공 %d, 실패 %d, 토큰 입력 %d / 출력 %d, 모델 %s",
        len(items),
        len(judged.judgments),
        len(judged.failed),
        judged.usage.input_tokens,
        judged.usage.output_tokens,
        judged.model or "-",
    )

    verification = {c.sentence.idx: _verification_for(c, evidence[c.sentence.idx], judged) for c in result.claims}
    return AnalysisOutcome(
        classification=result, evidence=evidence, verification=verification, judge_usage=judged.usage
    )
