from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import settings


class AnalyzeRequest(BaseModel):
    # 글자 수 상한은 스키마 단계에서 막는다. (공백만 있는 입력은 서비스 단계에서 따로 처리)
    text: str = Field(max_length=settings.max_input_chars)
    # true이고 X-Anon-Token 헤더가 있을 때만 입력 원문과 결과를 서버 DB에 저장한다. (기본: 저장 안 함)
    save: bool = False


class SourceOut(BaseModel):
    """검색으로 찾은 근거 후보 문서와, 그 발췌문을 주장과 비교한 결과."""

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
    # 저장 결과. not_requested(저장 안 함) | saved | failed(저장 실패, 분석 결과는 정상) | no_token(저장을 요청했지만 식별 정보 없음)
    save_status: str = "not_requested"
    analysis_id: str | None = None  # saved일 때만


class AnalysisDetail(BaseModel):
    """저장된 분석 하나. result는 분석 직후의 응답과 같은 형식이다."""

    id: str
    created_at: datetime
    text: str  # 분석을 요청했던 원문. result 안의 start/end는 이 글 기준이다.
    result: AnalyzeResponse


class AnalysisSummaryOut(BaseModel):
    id: str
    created_at: datetime
    preview: str  # 입력 원문의 앞부분
    sentence_count: int
    check_worthy_count: int
    # 검증 상태별 문장 수. 예: {"supported": 2, "insufficient": 1} ('검색된 출처 기준'의 참고 정보)
    status_counts: dict[str, int]


class DeleteResult(BaseModel):
    deleted: int
