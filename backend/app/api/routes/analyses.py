from fastapi import APIRouter

from app.schemas.analysis import AnalyzeRequest, AnalyzeResponse, ClaimOut, SourceOut
from app.services.pipeline import analyze_text
from app.services.text_offsets import utf16_offset_table

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("", response_model=AnalyzeResponse)
def create_analysis(body: AnalyzeRequest) -> AnalyzeResponse:
    """AI 답변을 문장별로 분석하고, 확인이 필요한 문장마다 위키백과에서 근거 후보를 찾는다.
    (지금은 DB에 저장하지 않는다. 저장은 9단계)

    동기(def) 함수로 둔 이유: Claude SDK와 검색 호출이 동기 방식이라, FastAPI가 별도 스레드에서
    실행해 다른 요청을 막지 않게 하기 위해서다.
    """
    outcome = analyze_text(body.text)
    table = utf16_offset_table(body.text)

    claims = []
    for c in outcome.classification.claims:
        ev = outcome.evidence[c.sentence.idx]
        claims.append(
            ClaimOut(
                idx=c.sentence.idx,
                text=c.sentence.text,
                start=table[c.sentence.start],
                end=table[c.sentence.end],
                claim_type=c.claim_type,
                check_worthy=c.check_worthy,
                # 확인 대상이 아닌 문장에는 취약점 신호를 보여 주지 않는다. (예: 제목에 '모든'이 있어도 표시 안 함)
                flags=c.flags if c.check_worthy else [],
                reason=c.reason,
                search_status=ev.status,
                search_query=c.search_query,
                search_error=ev.error,
                sources=[
                    SourceOut(title=r.title, url=r.url, snippet=r.snippet, source=r.source) for r in ev.results
                ],
            )
        )
    return AnalyzeResponse(
        claims=claims,
        sentence_count=len(claims),
        check_worthy_count=sum(c.check_worthy for c in claims),
        model=outcome.classification.model,
    )
