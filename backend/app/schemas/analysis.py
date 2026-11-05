from pydantic import BaseModel, Field

from app.core.config import settings


class AnalyzeRequest(BaseModel):
    # 글자 수 상한은 스키마 단계에서 막는다. (공백만 있는 입력은 서비스 단계에서 따로 처리)
    text: str = Field(max_length=settings.max_input_chars)


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


class AnalyzeResponse(BaseModel):
    claims: list[ClaimOut]
    sentence_count: int
    check_worthy_count: int
    model: str
