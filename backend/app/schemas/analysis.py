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


class AnalyzeResponse(BaseModel):
    claims: list[ClaimOut]
    sentence_count: int
    check_worthy_count: int
    model: str
