"""분리된 문장을 Claude에 보내 유형/확인 필요 여부/취약점 신호를 분류한다.

설계 원칙
- 문장 본문과 위치는 코드(sentence_splitter)가 정한다. Claude는 idx별 분류 결과만 돌려준다.
- Claude가 사실 여부를 판정하지 않는다. 분류와 '다시 확인해 볼 만한 신호'만 표시한다.
- Claude의 응답은 믿지 않고 검증한다. idx가 빠지거나 중복되거나 허용 값이 아니면 재시도 후 오류로 처리한다.
"""

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import anthropic

from app.core.config import settings
from app.models.enums import LLM_FLAGS, ClaimType
from app.prompts import load_prompt
from app.services.sentence_splitter import Sentence
from app.services.vulnerability_rules import detect_rule_flags

logger = logging.getLogger(__name__)

_MAX_REASON_CHARS = 200
_MAX_ATTEMPTS = 2  # 첫 시도 + 형식 오류 시 1회 재시도
_VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


class ClassificationError(Exception):
    """분류에 실패했다. (응답 형식 오류, 길이 초과 등)"""


class ClassificationRefusedError(ClassificationError):
    """모델이 안전 정책 때문에 응답을 거부했다."""


class LLMNotConfiguredError(ClassificationError):
    """ANTHROPIC_API_KEY가 설정되지 않았다."""


class TooManySentencesError(ClassificationError):
    """한 번에 분석할 수 있는 문장 수를 넘었다."""


@dataclass(frozen=True)
class ClaimAnalysis:
    sentence: Sentence
    claim_type: str
    check_worthy: bool
    flags: list[str]  # 코드 규칙 신호 + Claude 신호
    reason: str


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ClassificationResult:
    claims: list[ClaimAnalysis]
    model: str
    usage: TokenUsage = field(default_factory=TokenUsage)


_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "claim_type": {"type": "string", "enum": [t.value for t in ClaimType]},
                    "check_worthy": {"type": "boolean"},
                    "flags": {
                        "type": "array",
                        "items": {"type": "string", "enum": [f.value for f in LLM_FLAGS]},
                    },
                    "reason": {"type": "string"},
                },
                "required": ["idx", "claim_type", "check_worthy", "flags", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


@lru_cache
def get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise LLMNotConfiguredError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    # SDK의 기본 재시도(429/5xx/연결 오류, 지수 백오프)를 그대로 쓴다.
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60.0)


def build_user_message(sentences: list[Sentence]) -> str:
    # JSON으로 인코딩해서 보낸다: 문장 안의 따옴표나 태그 문자열이 입력 구조를 깨지 못하게 한다.
    payload = [{"idx": s.idx, "text": s.text} for s in sentences]
    return "다음 문장 목록을 분류하세요.\n\n" + json.dumps(payload, ensure_ascii=False)


def parse_and_validate(raw: str, sentences: list[Sentence]) -> list[ClaimAnalysis]:
    """모델 응답(JSON 문자열)을 검증하고 ClaimAnalysis 목록으로 바꾼다. 어긋나면 ValueError."""
    try:
        results = json.loads(raw)["results"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"응답이 올바른 JSON 형식이 아닙니다: {type(exc).__name__}") from exc

    if not isinstance(results, list) or not all(isinstance(item, dict) for item in results):
        raise ValueError("results가 객체 배열이 아닙니다.")

    by_idx: dict[int, dict[str, Any]] = {}
    for item in results:
        idx = item.get("idx")
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise ValueError("idx가 정수가 아닙니다.")
        if idx in by_idx:
            raise ValueError(f"idx {idx}가 중복되었습니다.")
        by_idx[idx] = item

    expected = {s.idx for s in sentences}
    if set(by_idx) != expected:
        missing = sorted(expected - set(by_idx))
        unknown = sorted(set(by_idx) - expected)
        raise ValueError(f"idx 불일치 (누락: {missing}, 없는 번호: {unknown})")

    allowed_types = {t.value for t in ClaimType}
    allowed_flags = {f.value for f in LLM_FLAGS}
    analyses: list[ClaimAnalysis] = []
    for sentence in sentences:
        item = by_idx[sentence.idx]
        if item.get("claim_type") not in allowed_types:
            raise ValueError(f"idx {sentence.idx}: 허용되지 않는 claim_type")
        if not isinstance(item.get("check_worthy"), bool):
            raise ValueError(f"idx {sentence.idx}: check_worthy가 불리언이 아닙니다.")
        llm_flags = item.get("flags")
        if not isinstance(llm_flags, list) or not set(llm_flags) <= allowed_flags:
            raise ValueError(f"idx {sentence.idx}: 허용되지 않는 flags")
        # 코드 규칙 신호를 앞에 두고, Claude 신호를 뒤에 붙인다. (중복 제거, 순서 유지)
        flags = list(dict.fromkeys([*detect_rule_flags(sentence.text), *llm_flags]))
        reason = str(item.get("reason", "")).strip()[:_MAX_REASON_CHARS]
        analyses.append(
            ClaimAnalysis(
                sentence=sentence,
                claim_type=item["claim_type"],
                check_worthy=item["check_worthy"],
                flags=flags,
                reason=reason,
            )
        )
    return analyses


def classify_sentences(
    sentences: list[Sentence], *, client: anthropic.Anthropic | None = None
) -> ClassificationResult:
    model = settings.extract_model
    if not sentences:
        return ClassificationResult(claims=[], model=model)
    if len(sentences) > settings.max_sentences:
        raise TooManySentencesError(
            f"문장이 {len(sentences)}개입니다. 한 번에 최대 {settings.max_sentences}개까지 분석할 수 있습니다."
        )
    effort = settings.extract_effort
    if effort not in _VALID_EFFORTS:
        raise ClassificationError(f"EXTRACT_EFFORT 값이 올바르지 않습니다: {effort}")

    client = client or get_client()
    usage = TokenUsage()
    last_problem = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=load_prompt("claim_classifier_system"),
            messages=[{"role": "user", "content": build_user_message(sentences)}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA},
            },
        )
        usage.input_tokens += response.usage.input_tokens
        usage.output_tokens += response.usage.output_tokens

        if response.stop_reason == "refusal":
            raise ClassificationRefusedError("모델이 이 입력의 분석을 거부했습니다.")
        if response.stop_reason == "max_tokens":
            raise ClassificationError("응답이 길이 제한에 걸려 잘렸습니다.")

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            claims = parse_and_validate(text, sentences)
        except ValueError as exc:
            last_problem = str(exc)
            logger.warning("분류 응답 검증 실패 (시도 %d/%d): %s", attempt, _MAX_ATTEMPTS, last_problem)
            continue
        return ClassificationResult(claims=claims, model=model, usage=usage)

    raise ClassificationError(f"모델 응답을 검증하지 못했습니다: {last_problem}")
