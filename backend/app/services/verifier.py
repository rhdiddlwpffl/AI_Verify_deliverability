"""검색된 문서의 발췌문이 주장을 뒷받침하는지 Claude로 비교하고, 코드가 그 결과를 검증한다.

설계 원칙
- Claude는 출처마다 stance(supports/contradicts/neutral)와 '인용문'만 돌려준다. 최종 상태는 모델이 정하지 않는다.
- 코드가 인용문이 발췌문에 실제로 있는지 글자 단위로 확인한다. 없으면 그 근거는 neutral로 낮춘다.
- 최종 상태는 '검증을 통과한 근거'만으로 코드가 계산한다. (설명하기 쉽고 모델이 조작할 수 없다)
- 이 상태는 '검색된 출처 기준의 참고 정보'이지 사실 여부의 확정 판정이 아니다.
- 한계: 인용문이 발췌문에 '실제로 있다'는 것과 그 인용이 주장을 '정말 뒷받침한다'는 것은 다르다.
  앞의 것만 코드가 확인한다. 그래서 화면에는 인용문과 원문 링크를 함께 보여 줘 사람이 읽을 수 있게 한다.
"""

import json
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.core.config import settings
from app.models.enums import Confidence, Stance, VerificationStatus
from app.prompts import load_prompt
from app.services.claim_extractor import TokenUsage, get_client
from app.services.searcher import SearchResult

logger = logging.getLogger(__name__)

_STANCES = [s.value for s in Stance]
_MIN_QUOTE_CHARS = 8  # 너무 짧은 인용('1889년')은 어디에나 있어서 근거로 인정하지 않는다
_MAX_QUOTE_CHARS = 300
_MAX_RATIONALE_CHARS = 200
_MAX_ATTEMPTS = 2  # 첫 시도 + 형식 오류 시 1회 재시도
_VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}

_INVISIBLE = re.compile("[\u200b\u2060\ufeff]")
# 이 도구는 '확정 판정'을 하지 않는다. 모델이 지시를 어기고 판정 표현을 쓰면 그 문장은 버린다.
_DEFINITIVE = re.compile(r"사실이다|사실입니다|사실임|거짓이다|거짓입니다|거짓임|틀렸|틀립니다|틀리다|맞습니다|맞다\b|정확합니다|정확하다|옳다|옳습니다")

# 모델에게 요구하는 응답 형식
JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx": {"type": "integer"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "sid": {"type": "integer"},
                                "stance": {"type": "string", "enum": _STANCES},
                                "same_scope": {"type": "boolean"},
                                "quote": {"type": "string"},
                            },
                            "required": ["sid", "stance", "same_scope", "quote"],
                            "additionalProperties": False,
                        },
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["idx", "sources", "rationale"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}

# 비교 입력 한 항목: (문장 번호, 주장 문장, 검색 결과 목록)
JudgeItem = tuple[int, str, list[SearchResult]]


@dataclass(frozen=True)
class SourceVerdict:
    sid: int
    stance: str  # 검증 후의 stance
    quote: str  # 검증을 통과한 인용문(발췌문의 실제 부분 문자열). 없으면 ""
    downgraded: bool  # 모델은 supports/contradicts라 했지만 인용문을 확인하지 못해 neutral로 낮춤


@dataclass(frozen=True)
class Judgment:
    idx: int
    source_verdicts: list[SourceVerdict]
    status: str  # VerificationStatus 값
    confidence: str  # Confidence 값 (근거 강도. 사실 여부의 확실성이 아니다)
    rationale: str


@dataclass
class JudgeResult:
    judgments: dict[int, Judgment] = field(default_factory=dict)
    failed: dict[int, str] = field(default_factory=dict)  # idx → 실패 이유 코드
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""


def system_prompt() -> str:
    return load_prompt("evidence_judge_system")


def build_user_message(items: list[JudgeItem]) -> str:
    """JSON으로 인코딩해서 보낸다: 문장이나 발췌문 안의 따옴표/태그 문자열이 입력 구조를 깨거나
    지시처럼 해석되지 못하게 하기 위해서다. (위키백과 본문도 신뢰할 수 없는 입력으로 다룬다)"""
    payload = [
        {
            "idx": idx,
            "claim": claim,
            "sources": [{"sid": sid, "title": r.title, "excerpt": r.snippet} for sid, r in enumerate(results)],
        }
        for idx, claim, results in items
    ]
    return "다음 주장과 발췌문을 비교하세요.\n\n" + json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------- 인용문 검증


def _normalize(text: str) -> str:
    """비교용 정규화: 유니코드 NFC, 보이지 않는 글자 제거, 공백 정리."""
    return " ".join(unicodedata.normalize("NFC", _INVISIBLE.sub("", text)).split())


def find_quote(quote: str, snippet: str) -> str | None:
    """인용문이 발췌문에 실제로 있으면, 발췌문 안의 '실제 부분 문자열'을 돌려준다. 없으면 None.

    돌려주는 값이 모델이 쓴 quote가 아니라 발췌문의 실제 글자인 이유: 화면에서 발췌문 안에
    그대로 찾아 강조할 수 있고, 공백 차이 같은 사소한 어긋남이 남지 않게 하기 위해서다.
    """
    q, s = _normalize(quote), _normalize(snippet)
    if not (_MIN_QUOTE_CHARS <= len(q) <= _MAX_QUOTE_CHARS):
        return None
    pos = s.find(q)
    return s[pos : pos + len(q)] if pos != -1 else None


def derive_status(verdicts: list[SourceVerdict]) -> tuple[str, str]:
    """검증을 통과한 근거만으로 (상태, 근거 강도)를 계산한다. 모델의 판단은 쓰지 않는다."""
    supports = sum(v.stance == Stance.SUPPORTS.value for v in verdicts)
    contradicts = sum(v.stance == Stance.CONTRADICTS.value for v in verdicts)

    if supports and contradicts:
        return VerificationStatus.MIXED.value, Confidence.LOW.value
    if supports or contradicts:
        status = VerificationStatus.SUPPORTED if supports else VerificationStatus.CONTRADICTED
        # '근거 강도'는 검증된 인용이 몇 건인지만 반영한다. 사실 여부의 확실성이 아니다.
        confidence = Confidence.HIGH if max(supports, contradicts) >= 2 else Confidence.MEDIUM
        return status.value, confidence.value
    return VerificationStatus.INSUFFICIENT.value, Confidence.LOW.value


def _clean_rationale(text: Any) -> str:
    rationale = str(text or "").strip()[:_MAX_RATIONALE_CHARS]
    if _DEFINITIVE.search(rationale):
        logger.warning("비교 요약에 확정 판정 표현이 있어 버렸습니다.")
        return ""
    return rationale


def parse_and_verify(raw: str, items: list[JudgeItem]) -> dict[int, Judgment]:
    """모델 응답을 구조 검증하고, 인용문을 글자 단위로 검증해서 Judgment로 만든다. 구조가 어긋나면 ValueError."""
    try:
        results = json.loads(raw)["results"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"응답이 올바른 JSON 형식이 아닙니다: {type(exc).__name__}") from exc
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        raise ValueError("results가 객체 배열이 아닙니다.")

    by_idx: dict[int, dict[str, Any]] = {}
    for r in results:
        idx = r.get("idx")
        if not isinstance(idx, int) or isinstance(idx, bool):
            raise ValueError("idx가 정수가 아닙니다.")
        if idx in by_idx:
            raise ValueError(f"idx {idx}가 중복되었습니다.")
        by_idx[idx] = r
    expected = {idx for idx, _, _ in items}
    if set(by_idx) != expected:
        raise ValueError(f"idx 불일치 (누락: {sorted(expected - set(by_idx))}, 없는 번호: {sorted(set(by_idx) - expected)})")

    judgments: dict[int, Judgment] = {}
    for idx, _claim, sources in items:
        entry = by_idx[idx]
        raw_sources = entry.get("sources")
        if not isinstance(raw_sources, list) or not all(isinstance(s, dict) for s in raw_sources):
            raise ValueError(f"idx {idx}: sources가 객체 배열이 아닙니다.")
        by_sid: dict[int, dict[str, Any]] = {}
        for s in raw_sources:
            sid = s.get("sid")
            if not isinstance(sid, int) or isinstance(sid, bool) or sid in by_sid:
                raise ValueError(f"idx {idx}: sid가 올바르지 않거나 중복되었습니다.")
            by_sid[sid] = s
        if set(by_sid) != set(range(len(sources))):
            raise ValueError(f"idx {idx}: sid 불일치")

        verdicts: list[SourceVerdict] = []
        for sid, result in enumerate(sources):
            s = by_sid[sid]
            stance, quote = s.get("stance"), s.get("quote")
            if stance not in _STANCES:
                raise ValueError(f"idx {idx}, sid {sid}: 허용되지 않는 stance")
            if not isinstance(quote, str):
                raise ValueError(f"idx {idx}, sid {sid}: quote가 문자열이 아닙니다.")
            same_scope = s.get("same_scope")
            if not isinstance(same_scope, bool):
                raise ValueError(f"idx {idx}, sid {sid}: same_scope가 불리언이 아닙니다.")

            if stance == Stance.NEUTRAL.value:
                verdicts.append(SourceVerdict(sid, Stance.NEUTRAL.value, "", False))
                continue
            real_quote = find_quote(quote, result.snippet)
            if real_quote is None or not same_scope:
                # 근거로 인정하지 않는다: 인용문이 발췌문에 없거나, 발췌문이 주장과 다른 대상/시점/범위를 다룬다.
                # (예: 주장은 2023년 통계인데 발췌문은 2022년 통계. 인용문이 실제로 있어도 반박이 아니다)
                verdicts.append(SourceVerdict(sid, Stance.NEUTRAL.value, "", True))
            else:
                verdicts.append(SourceVerdict(sid, stance, real_quote, False))

        status, confidence = derive_status(verdicts)
        judgments[idx] = Judgment(
            idx=idx,
            source_verdicts=verdicts,
            status=status,
            confidence=confidence,
            rationale=_clean_rationale(entry.get("rationale")),
        )
    return judgments


# ---------------------------------------------------------------- 비교 호출


def _chunks(items: list[JudgeItem], size: int) -> list[list[JudgeItem]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _failure_code(exc: Exception) -> str:
    if isinstance(exc, anthropic.RateLimitError):
        return "rate_limited"
    if isinstance(exc, anthropic.APITimeoutError):
        return "timeout"
    if isinstance(exc, anthropic.APIConnectionError):
        return "unavailable"
    return "error"


def _judge_chunk(
    client: anthropic.Anthropic, chunk: list[JudgeItem], usage: TokenUsage
) -> dict[int, Judgment]:
    """한 묶음을 비교한다. 형식 오류면 1회 재시도하고, 그래도 안 되면 ValueError."""
    last_problem = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        response = client.messages.create(
            model=settings.judge_model,
            max_tokens=16000,
            system=system_prompt(),
            messages=[{"role": "user", "content": build_user_message(chunk)}],
            output_config={
                "effort": settings.judge_effort,
                "format": {"type": "json_schema", "schema": JUDGE_SCHEMA},
            },
        )
        usage.input_tokens += response.usage.input_tokens
        usage.output_tokens += response.usage.output_tokens

        if response.stop_reason == "refusal":
            raise ValueError("refused")
        if response.stop_reason == "max_tokens":
            raise ValueError("truncated")
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return parse_and_verify(text, chunk)
        except ValueError as exc:
            last_problem = str(exc)
            logger.warning("비교 응답 검증 실패 (시도 %d/%d): %s", attempt, _MAX_ATTEMPTS, last_problem)
    raise ValueError(f"invalid_response: {last_problem}")


def judge_claims(items: list[JudgeItem], *, client: anthropic.Anthropic | None = None) -> JudgeResult:
    """발췌문이 있는 문장들을 묶음으로 나눠 병렬로 비교한다. 한 묶음이 실패해도 나머지는 살린다."""
    result = JudgeResult(model=settings.judge_model)
    if not items:
        return result
    if settings.judge_effort not in _VALID_EFFORTS:
        raise ValueError(f"JUDGE_EFFORT 값이 올바르지 않습니다: {settings.judge_effort}")
    client = client or get_client()

    def run(chunk: list[JudgeItem]) -> tuple[list[JudgeItem], dict[int, Judgment] | str, TokenUsage]:
        usage = TokenUsage()
        try:
            return chunk, _judge_chunk(client, chunk, usage), usage
        except anthropic.AnthropicError as exc:
            logger.error("비교 호출 오류: %s", type(exc).__name__)
            return chunk, _failure_code(exc), usage
        except ValueError as exc:
            logger.error("비교 결과를 사용할 수 없음: %s", str(exc).split(":")[0])
            return chunk, "judge_failed", usage

    with ThreadPoolExecutor(max_workers=max(1, settings.judge_concurrency)) as pool:
        outcomes = list(pool.map(run, _chunks(items, max(1, settings.judge_chunk_size))))

    for chunk, outcome, usage in outcomes:
        result.usage.input_tokens += usage.input_tokens
        result.usage.output_tokens += usage.output_tokens
        if isinstance(outcome, str):
            for idx, _, _ in chunk:
                result.failed[idx] = outcome
        else:
            result.judgments.update(outcome)
    return result
