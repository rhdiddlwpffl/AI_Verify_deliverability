from pydantic import BaseModel, Field

from app.core.config import settings


class AnalyzeRequest(BaseModel):
    # 글자 수 상한은 스키마 단계에서 막는다. (공백만 있는 입력은 서비스 단계에서 따로 처리)
    text: str = Field(max_length=settings.max_input_chars)


class SourceOut(BaseModel):
    """검색으로 찾은 근거 후보 문서. 이 문서가 주장을 뒷받침하는지는 아직 판단하지 않은 상태다."""

    title: str
    url: str
    snippet: str  # 문서 도입부 본문(순수 텍스트)
    source: str  # 어디서 찾았는지. 예: "wikipedia-ko"
    # 비교 결과(비교하지 못했으면 stance는 null). 'supports'/'contradicts'는 인용문이 발췌문에
    # 실제로 있음을 코드가 확인한 경우에만 나온다. 이것이 주장이 참/거짓이라는 뜻은 아니다.
    stance: str | None
    quote: str  # 검증을 통과한 인용문(snippet 안의 실제 부분 문자열). 없으면 ""
    downgraded: bool  # AI는 근거라고 했지만 인용문을 확인할 수 없어 근거에서 제외한 경우


class ClaimOut(BaseModel):
    idx: int
    text: str
    # 요청한 text 안에서의 위치. JavaScript의 text.slice(start, end)와 그대로 맞는다. (UTF-16 기준)
    start: int
    end: int
    claim_type: str
    check_worthy: bool
    # 취약점 신호는 '다시 확인해 볼 만한 특징'일 뿐 거짓 판정이 아니다.
    # 확인 대상이 아닌 문장(check_worthy=false)에는 빈 배열로 내려보낸다.
    flags: list[str]
    reason: str
    # 검색: not_searched(확인 대상 아님) | found(문서를 찾음) | none(찾지 못함) | failed(검색 실패) | skipped(개수 제한)
    # 'none'(정상 검색, 결과 없음)과 'failed'(검색 자체가 실패)는 다른 상황이다.
    search_status: str
    search_query: str
    search_error: str | None  # failed일 때만: rate_limited | unavailable | timeout | error
    sources: list[SourceOut]
    # 검색된 출처 기준의 참고용 상태. 확정 판정이 아니다.
    # not_checkable | supported | contradicted | mixed | insufficient | search_failed | unverified
    verification_status: str
    verification_confidence: str | None  # high | medium | low. 검증된 인용 수에 따른 '근거 강도'이며 사실 여부의 확실성이 아니다
    verification_rationale: str | None  # 발췌문에서 무엇이 확인/미확인인지 요약
    verification_error: str | None  # unverified일 때 이유: skipped | judge_failed | rate_limited | timeout | unavailable | error


class AnalyzeResponse(BaseModel):
    claims: list[ClaimOut]
    sentence_count: int
    check_worthy_count: int
    model: str
