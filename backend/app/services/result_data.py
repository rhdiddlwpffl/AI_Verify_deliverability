"""분석 결과를 담는 중간 구조.

'방금 분석한 결과(pipeline)'와 'DB에서 읽은 결과(repository)'를 같은 구조로 맞춘 뒤,
응답은 to_response 한 곳에서만 만든다. 그래서 저장 후 읽어도 응답이 어긋나지 않는다.
위치(start/end)는 파이썬 글자 위치(코드 포인트)로 들고 있다가, 응답을 만들 때만 JavaScript 기준으로 바꾼다.
"""

from dataclasses import dataclass, field
from typing import Any

from app.schemas.analysis import AnalyzeResponse, ClaimOut, SourceOut
from app.services.pipeline import AnalysisOutcome
from app.services.text_offsets import utf16_offset_table


@dataclass
class SourceData:
    title: str
    url: str
    snippet: str
    source: str  # 예: "wikipedia-ko"
    stance: str | None  # 비교하지 못했으면 None
    quote: str
    downgraded: bool


@dataclass
class ClaimData:
    idx: int
    text: str
    start: int  # 파이썬 글자 위치
    end: int
    claim_type: str
    check_worthy: bool
    flags: list[str]  # 가공하지 않은 값. 확인 대상이 아닌 문장의 신호를 숨기는 일은 to_response가 한다.
    reason: str
    search_status: str
    search_query: str
    search_error: str | None
    sources: list[SourceData]
    verification_status: str
    verification_confidence: str | None
    verification_rationale: str | None
    verification_error: str | None


@dataclass
class ResultData:
    claims: list[ClaimData]
    model: str  # 분류에 쓴 모델
    # 저장용 부가 정보(응답에는 포함하지 않는다). 예: 비교 모델, 토큰 사용량
    model_info: dict[str, Any] = field(default_factory=dict)


def from_outcome(outcome: AnalysisOutcome) -> ResultData:
    claims: list[ClaimData] = []
    for c in outcome.classification.claims:
        idx = c.sentence.idx
        ev = outcome.evidence[idx]
        vr = outcome.verification[idx]
        verdicts = vr.source_verdicts  # 비교에 성공했을 때만 있다. 출처 순서와 같은 순서.
        claims.append(
            ClaimData(
                idx=idx,
                text=c.sentence.text,
                start=c.sentence.start,
                end=c.sentence.end,
                claim_type=c.claim_type,
                check_worthy=c.check_worthy,
                flags=list(c.flags),
                reason=c.reason,
                search_status=ev.status,
                search_query=c.search_query,
                search_error=ev.error,
                sources=[
                    SourceData(
                        title=r.title,
                        url=r.url,
                        snippet=r.snippet,
                        source=r.source,
                        stance=verdicts[i].stance if verdicts else None,
                        quote=verdicts[i].quote if verdicts else "",
                        downgraded=verdicts[i].downgraded if verdicts else False,
                    )
                    for i, r in enumerate(ev.results)
                ],
                verification_status=vr.status,
                verification_confidence=vr.confidence,
                verification_rationale=vr.rationale,
                verification_error=vr.error,
            )
        )
    cu, ju = outcome.classification.usage, outcome.judge_usage
    return ResultData(
        claims=claims,
        model=outcome.classification.model,
        model_info={
            "classification_model": outcome.classification.model,
            "judge_model": outcome.judge_model,
            "tokens": {
                "classification": {"input": cu.input_tokens, "output": cu.output_tokens},
                "judge": {"input": ju.input_tokens, "output": ju.output_tokens},
            },
        },
    )


def to_response(text: str, data: ResultData) -> AnalyzeResponse:
    table = utf16_offset_table(text)
    claims = [
        ClaimOut(
            idx=c.idx,
            text=c.text,
            start=table[c.start],
            end=table[c.end],
            claim_type=c.claim_type,
            check_worthy=c.check_worthy,
            # 확인 대상이 아닌 문장에는 취약점 신호를 보여 주지 않는다. (예: 제목에 '모든'이 있어도 표시 안 함)
            flags=c.flags if c.check_worthy else [],
            reason=c.reason,
            search_status=c.search_status,
            search_query=c.search_query,
            search_error=c.search_error,
            sources=[
                SourceOut(
                    title=s.title,
                    url=s.url,
                    snippet=s.snippet,
                    source=s.source,
                    stance=s.stance,
                    quote=s.quote,
                    downgraded=s.downgraded,
                )
                for s in c.sources
            ],
            verification_status=c.verification_status,
            verification_confidence=c.verification_confidence,
            verification_rationale=c.verification_rationale,
            verification_error=c.verification_error,
        )
        for c in data.claims
    ]
    return AnalyzeResponse(
        claims=claims,
        sentence_count=len(claims),
        check_worthy_count=sum(c.check_worthy for c in claims),
        model=data.model,
    )
