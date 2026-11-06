import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import optional_token_hash, required_token_hash
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_engine, get_session
from app.schemas.analysis import (
    AnalysisDetail,
    AnalysisSummaryOut,
    AnalyzeRequest,
    AnalyzeResponse,
    DeleteResult,
)
from app.services import repository
from app.services.pipeline import analyze_text
from app.services.result_data import ResultData, from_outcome, to_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analyses", tags=["analyses"])

TokenHash = Annotated[str, Depends(required_token_hash)]
DbSession = Annotated[Session, Depends(get_session)]


def _try_save(token_hash: str | None, text: str, data: ResultData) -> tuple[str, str | None]:
    """(save_status, analysis_id). 저장이 실패해도 분석 결과는 사용자에게 돌려준다."""
    if token_hash is None:
        return "no_token", None
    try:
        # 분석에 10~20초가 걸리므로, DB 연결은 저장할 때만 잡는다.
        with Session(get_engine()) as session:
            analysis_id = repository.save_analysis(session, token_hash, text, data)
            session.commit()
            try:
                repository.cleanup_expired(session, settings.retention_days)
                session.commit()
            except Exception as exc:  # noqa: BLE001  정리 실패가 저장 성공을 뒤집으면 안 된다
                session.rollback()
                logger.warning("만료 기록 정리 실패: %s", type(exc).__name__)
        return "saved", str(analysis_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("분석 결과 저장 실패: %s", type(exc).__name__)
        return "failed", None


@router.post("", response_model=AnalyzeResponse)
def create_analysis(
    body: AnalyzeRequest, token_hash: Annotated[str | None, Depends(optional_token_hash)]
) -> AnalyzeResponse:
    """AI 답변을 문장별로 분석하고, 확인이 필요한 문장마다 위키백과 근거를 찾아 비교한다.
    body.save가 true이고 X-Anon-Token 헤더가 있을 때만 입력 원문과 결과를 DB에 저장한다.

    동기(def) 함수로 둔 이유: Claude SDK와 검색 호출이 동기 방식이라, FastAPI가 별도 스레드에서
    실행해 다른 요청을 막지 않게 하기 위해서다.
    """
    outcome = analyze_text(body.text)
    data = from_outcome(outcome)
    response = to_response(body.text, data)
    if body.save:
        response.save_status, response.analysis_id = _try_save(token_hash, body.text, data)
    return response


@router.get("", response_model=list[AnalysisSummaryOut])
def list_my_analyses(
    token_hash: TokenHash,
    session: DbSession,
    limit: Annotated[int, Query(ge=1)] = settings.history_page_size,
) -> list[AnalysisSummaryOut]:
    """내 기록 목록(최신순)."""
    summaries = repository.list_analyses(session, token_hash, min(limit, settings.history_page_size))
    return [
        AnalysisSummaryOut(
            id=str(s.id),
            created_at=s.created_at,
            preview=s.preview,
            sentence_count=s.sentence_count,
            check_worthy_count=s.check_worthy_count,
            status_counts=s.status_counts,
        )
        for s in summaries
    ]


@router.get("/{analysis_id}", response_model=AnalysisDetail)
def get_my_analysis(analysis_id: UUID, token_hash: TokenHash, session: DbSession) -> AnalysisDetail:
    stored = repository.load_analysis(session, token_hash, analysis_id)
    if stored is None:  # 없는 기록이든 남의 기록이든 똑같이 404
        raise AppError(404, "not_found", "해당 기록을 찾을 수 없습니다. 이미 삭제되었거나 보관 기간이 지났을 수 있습니다.")
    return AnalysisDetail(
        id=str(stored.id),
        created_at=stored.created_at,
        text=stored.text,
        result=to_response(stored.text, stored.data),
    )


@router.delete("/{analysis_id}", response_model=DeleteResult)
def delete_my_analysis(analysis_id: UUID, token_hash: TokenHash, session: DbSession) -> DeleteResult:
    if not repository.delete_analysis(session, token_hash, analysis_id):
        raise AppError(404, "not_found", "해당 기록을 찾을 수 없습니다. 이미 삭제되었을 수 있습니다.")
    session.commit()
    return DeleteResult(deleted=1)


@router.delete("", response_model=DeleteResult)
def delete_all_my_analyses(token_hash: TokenHash, session: DbSession) -> DeleteResult:
    """내 기록 전체 삭제."""
    deleted = repository.delete_all(session, token_hash)
    session.commit()
    return DeleteResult(deleted=deleted)
