"""Claude/내부 오류가 사용자에게 어떤 오류로 나가는지 확인한다.
핵심: (1) 상태 코드와 코드가 구분되어 있다 (2) 메시지에 키, 접속 정보, 예외 원문이 섞이지 않는다."""

import anthropic
import httpx2
import pytest

from app.core.config import settings
from app.core.errors import AppError
from app.services import pipeline
from app.services.claim_extractor import (
    ClassificationError,
    ClassificationRefusedError,
    LLMNotConfiguredError,
    TooManySentencesError,
)
from app.services.pipeline import analyze_text, precheck
from tests.fakes import patched

# 가짜 값이다. 소스에 키 모양 문자열을 그대로 적으면 비밀값 스캐너가 실제 키로 오인하므로 조립해서 만든다.
KEY_PREFIX = "sk-" + "ant"
SECRET = KEY_PREFIX + "-api03-FAKE-should-never-leak"
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def api_error(cls, status):
    response = httpx2.Response(status, request=REQUEST, json={"error": {"message": SECRET}})
    return cls(SECRET, response=response, body=None)


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (api_error(anthropic.RateLimitError, 429), 429, "llm_rate_limited"),
        (api_error(anthropic.AuthenticationError, 401), 502, "llm_auth_error"),
        (api_error(anthropic.PermissionDeniedError, 403), 502, "llm_auth_error"),
        (api_error(anthropic.BadRequestError, 400), 502, "llm_request_error"),  # 예: 크레딧 소진
        (api_error(anthropic.InternalServerError, 500), 502, "llm_error"),
        (anthropic.APITimeoutError(request=REQUEST), 504, "llm_timeout"),
        (anthropic.APIConnectionError(request=REQUEST), 502, "llm_unavailable"),
    ],
)
def test_claude_errors_become_distinct_user_errors_without_leaking_details(exc, status, code):
    err = pipeline._llm_error(exc)
    assert (err.status_code, err.code) == (status, code)
    assert SECRET not in err.message and KEY_PREFIX not in err.message
    assert err.message.strip()  # 사용자에게 보여 줄 한국어 문장이 있다


@pytest.mark.parametrize(
    ("raised", "status", "code"),
    [
        (TooManySentencesError("문장이 99개입니다. 한 번에 최대 60개까지 분석할 수 있습니다."), 422, "too_many_sentences"),
        (ClassificationRefusedError("refused"), 422, "analysis_refused"),
        (LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다."), 503, "llm_not_configured"),
        (ClassificationError(f"내부 원인 {SECRET}"), 502, "analysis_failed"),
        (api_error(anthropic.RateLimitError, 429), 429, "llm_rate_limited"),
    ],
)
def test_analyze_text_maps_classification_failures(raised, status, code):
    def boom(sentences):
        raise raised

    original = pipeline.classify_sentences
    pipeline.classify_sentences = boom
    try:
        with pytest.raises(AppError) as exc:
            analyze_text("에펠탑은 1889년에 지어졌다.")
    finally:
        pipeline.classify_sentences = original
    assert (exc.value.status_code, exc.value.code) == (status, code)
    assert SECRET not in exc.value.message


def test_unexpected_exceptions_are_not_swallowed_as_user_errors():
    def boom(sentences):
        raise RuntimeError("프로그램 버그")

    original = pipeline.classify_sentences
    pipeline.classify_sentences = boom
    try:
        with pytest.raises(RuntimeError):  # 버그는 숨기지 않고 500 핸들러까지 올라가야 한다
            analyze_text("에펠탑은 1889년에 지어졌다.")
    finally:
        pipeline.classify_sentences = original


def test_precheck_rejects_bad_input_before_any_cost():
    for text, code in (("   \n", "empty_input"), ("```\nx = 1\n```", "no_sentences")):
        with pytest.raises(AppError) as exc:
            precheck(text)
        assert (exc.value.status_code, exc.value.code) == (422, code)

    saved = settings.max_sentences
    settings.max_sentences = 2
    try:
        with pytest.raises(AppError) as exc:
            precheck("하나. 둘. 셋.")
        assert exc.value.code == "too_many_sentences" and "3개" in exc.value.message
        assert len(precheck("하나. 둘.")) == 2  # 상한 이하는 통과하고 문장 목록을 돌려준다
    finally:
        settings.max_sentences = saved


def test_judge_configuration_error_degrades_to_unverified_instead_of_failing_the_analysis():
    def broken_judge(items):
        raise ValueError("JUDGE_EFFORT 값이 올바르지 않습니다: turbo")

    with patched(judge=broken_judge):
        outcome = analyze_text("😀 에펠탑은 1889년에 지어졌다. 이 문장은 검색이 실패한다. 정말 멋지다.")

    by_idx = outcome.verification
    assert by_idx[0].status == "unverified" and by_idx[0].error == "judge_failed"  # 찾은 문서는 있으나 비교 불가
    assert by_idx[1].status == "search_failed"  # 검색 실패는 그대로
    assert by_idx[2].status == "not_checkable"
    assert len(outcome.evidence[0].results) == 2  # 비교가 실패해도 찾은 문서는 그대로 보여 준다
