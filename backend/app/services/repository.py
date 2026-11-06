"""분석 결과의 저장, 조회, 삭제.

- 이 모듈의 함수는 flush까지만 한다. commit은 호출하는 쪽(라우트)이 한다.
- 조회와 삭제는 토큰 해시가 맞는 기록만 대상으로 한다. 다른 사람의 기록은 '없는 것'처럼 다룬다.
- 같은 URL의 출처(sources)는 여러 분석이 공유한다. 주장과 출처의 연결(claim_sources)에는
  그 분석에서 본 발췌문, 순서, 비교 결과를 둔다.
- '비교하지 못함'(stance=None)은 DB에 따로 저장하지 않는다. claim_sources.stance는 NOT NULL이라
  neutral로 저장하고, 읽을 때 그 문장의 검증 상태가 unverified이면 None으로 되돌린다.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import case, delete, exists, func
from sqlalchemy import select as sa_select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from app.models import Analysis, Claim, ClaimSource, Source, Verification
from app.models.enums import AnalysisStatus, Stance, VerificationStatus
from app.services.result_data import ClaimData, ResultData, SourceData

logger = logging.getLogger(__name__)

_PREVIEW_CHARS = 80


@dataclass
class StoredAnalysis:
    id: UUID
    created_at: datetime
    text: str
    data: ResultData


@dataclass
class AnalysisSummary:
    id: UUID
    created_at: datetime
    preview: str
    sentence_count: int
    check_worthy_count: int
    status_counts: dict[str, int]


def _provider_from_domain(domain: str | None) -> str:
    """sources.domain에서 'wikipedia-ko' 같은 제공자 이름을 되살린다."""
    if domain and domain.endswith(".wikipedia.org"):
        return f"wikipedia-{domain.split('.')[0]}"
    return domain or "unknown"


# ------------------------------------------------------------------ 저장


def save_analysis(session: Session, token_hash: str, text: str, data: ResultData) -> UUID:
    analysis = Analysis(
        anon_token_hash=token_hash,
        input_text=text,
        status=AnalysisStatus.DONE.value,
        model_info=data.model_info,
    )
    session.add(analysis)
    session.flush()

    claim_rows: list[tuple[ClaimData, Claim]] = []
    for c in data.claims:
        row = Claim(
            analysis_id=analysis.id,
            idx=c.idx,
            sentence_text=c.text,
            start_offset=c.start,
            end_offset=c.end,
            claim_type=c.claim_type,
            check_worthy=c.check_worthy,
            vulnerability_flags=list(c.flags),
            reason=c.reason or None,
            search_query=c.search_query or None,
            search_status=c.search_status,
            search_error=c.search_error,
        )
        session.add(row)
        claim_rows.append((c, row))
    session.flush()

    now = datetime.now(UTC)
    source_ids: dict[str, UUID] = {}
    judge_model = data.model_info.get("judge_model")
    sources_table = Source.__table__

    for c, row in claim_rows:
        used_urls: set[str] = set()
        for position, s in enumerate(c.sources):
            if s.url in used_urls:  # (claim_id, source_id)가 기본키라 같은 문서를 두 번 넣을 수 없다
                continue
            used_urls.add(s.url)
            source_id = source_ids.get(s.url)
            if source_id is None:
                # 같은 URL이 이미 있으면 제목과 시각만 갱신한다. (동시에 저장해도 안전한 upsert)
                stmt = (
                    pg_insert(sources_table)
                    .values(id=uuid4(), url=s.url, title=s.title, domain=urlparse(s.url).netloc or None, fetched_at=now)
                    .on_conflict_do_update(index_elements=[sources_table.c.url], set_={"title": s.title, "fetched_at": now})
                    .returning(sources_table.c.id)
                )
                source_id = session.exec(stmt).scalar_one()
                source_ids[s.url] = source_id
            session.add(
                ClaimSource(
                    claim_id=row.id,
                    source_id=source_id,
                    position=position,
                    snippet=s.snippet,
                    stance=s.stance or Stance.NEUTRAL.value,
                    quoted_text=s.quote or None,
                    quote_verified=bool(s.quote),
                    downgraded=s.downgraded,
                )
            )
        judged = any(s.stance is not None for s in c.sources)
        session.add(
            Verification(
                claim_id=row.id,
                status=c.verification_status,
                confidence=c.verification_confidence,
                rationale=c.verification_rationale,
                error=c.verification_error,
                model=judge_model if judged else None,
            )
        )
    session.flush()
    return analysis.id


# ------------------------------------------------------------------ 조회


def load_analysis(session: Session, token_hash: str, analysis_id: UUID) -> StoredAnalysis | None:
    analysis = session.exec(
        select(Analysis).where(Analysis.id == analysis_id, Analysis.anon_token_hash == token_hash)
    ).first()
    if analysis is None:
        return None  # 없는 기록이든 남의 기록이든 똑같이 '없음'

    claims = session.exec(select(Claim).where(Claim.analysis_id == analysis.id).order_by(Claim.idx)).all()
    claim_ids = [c.id for c in claims]

    verifications: dict[UUID, Verification] = {}
    for v in session.exec(
        select(Verification).where(Verification.claim_id.in_(claim_ids)).order_by(Verification.created_at)
    ):
        verifications[v.claim_id] = v  # 같은 문장에 여러 개면 가장 최근 것이 남는다

    sources_by_claim: dict[UUID, list[tuple[ClaimSource, Source]]] = {}
    rows = session.exec(
        select(ClaimSource, Source)
        .join(Source, Source.id == ClaimSource.source_id)
        .where(ClaimSource.claim_id.in_(claim_ids))
        .order_by(ClaimSource.claim_id, ClaimSource.position)
    )
    for cs, src in rows:
        sources_by_claim.setdefault(cs.claim_id, []).append((cs, src))

    claim_data: list[ClaimData] = []
    for c in claims:
        v = verifications.get(c.id)
        status = v.status if v else (
            VerificationStatus.UNVERIFIED.value if c.check_worthy else VerificationStatus.NOT_CHECKABLE.value
        )
        not_compared = status == VerificationStatus.UNVERIFIED.value
        claim_data.append(
            ClaimData(
                idx=c.idx,
                text=c.sentence_text,
                start=c.start_offset,
                end=c.end_offset,
                claim_type=c.claim_type,
                check_worthy=c.check_worthy,
                flags=list(c.vulnerability_flags),
                reason=c.reason or "",
                search_status=c.search_status,
                search_query=c.search_query or "",
                search_error=c.search_error,
                sources=[
                    SourceData(
                        title=src.title or "",
                        url=src.url,
                        snippet=cs.snippet or "",
                        source=_provider_from_domain(src.domain),
                        stance=None if not_compared else cs.stance,
                        quote=cs.quoted_text or "",
                        downgraded=cs.downgraded,
                    )
                    for cs, src in sources_by_claim.get(c.id, [])
                ],
                verification_status=status,
                verification_confidence=v.confidence if v else None,
                verification_rationale=v.rationale if v else None,
                verification_error=v.error if v else None,
            )
        )

    info = analysis.model_info or {}
    return StoredAnalysis(
        id=analysis.id,
        created_at=analysis.created_at,
        text=analysis.input_text,
        data=ResultData(claims=claim_data, model=info.get("classification_model", ""), model_info=dict(info)),
    )


def list_analyses(session: Session, token_hash: str, limit: int) -> list[AnalysisSummary]:
    rows = session.exec(
        select(Analysis.id, Analysis.created_at, func.left(Analysis.input_text, 200))
        .where(Analysis.anon_token_hash == token_hash)
        .order_by(Analysis.created_at.desc(), Analysis.id)
        .limit(limit)
    ).all()
    if not rows:
        return []
    ids = [r[0] for r in rows]

    counts = {
        aid: (total, worthy)
        for aid, total, worthy in session.exec(
            select(
                Claim.analysis_id,
                func.count(),
                func.coalesce(func.sum(case((Claim.check_worthy, 1), else_=0)), 0),
            )
            .where(Claim.analysis_id.in_(ids))
            .group_by(Claim.analysis_id)
        )
    }
    status_counts: dict[UUID, dict[str, int]] = {}
    for aid, status, n in session.exec(
        select(Claim.analysis_id, Verification.status, func.count())
        .join(Verification, Verification.claim_id == Claim.id)
        .where(Claim.analysis_id.in_(ids), Verification.status != VerificationStatus.NOT_CHECKABLE.value)
        .group_by(Claim.analysis_id, Verification.status)
    ):
        status_counts.setdefault(aid, {})[status] = n

    summaries = []
    for aid, created_at, head in rows:
        flat = " ".join((head or "").split())
        preview = flat[:_PREVIEW_CHARS] + ("…" if len(flat) > _PREVIEW_CHARS else "")
        total, worthy = counts.get(aid, (0, 0))
        summaries.append(
            AnalysisSummary(aid, created_at, preview, int(total), int(worthy), status_counts.get(aid, {}))
        )
    return summaries


# ------------------------------------------------------------------ 삭제


def _delete_orphan_sources(session: Session) -> None:
    """어떤 분석도 참조하지 않는 출처를 지운다. (출처는 여러 분석이 공유하므로 분석 삭제 때 함께 지우지 않는다)"""
    session.exec(delete(Source).where(~exists(sa_select(ClaimSource.claim_id).where(ClaimSource.source_id == Source.id))))


def delete_analysis(session: Session, token_hash: str, analysis_id: UUID) -> bool:
    result = session.exec(delete(Analysis).where(Analysis.id == analysis_id, Analysis.anon_token_hash == token_hash))
    deleted = result.rowcount > 0
    if deleted:
        _delete_orphan_sources(session)
    return deleted


def delete_all(session: Session, token_hash: str) -> int:
    result = session.exec(delete(Analysis).where(Analysis.anon_token_hash == token_hash))
    if result.rowcount:
        _delete_orphan_sources(session)
    return result.rowcount


def cleanup_expired(session: Session, retention_days: int) -> int:
    """보관 기간이 지난 기록을 지운다. 별도 스케줄러 없이 저장할 때마다 함께 호출한다. (0이면 하지 않음)"""
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    result = session.exec(delete(Analysis).where(Analysis.created_at < cutoff))
    if result.rowcount:
        _delete_orphan_sources(session)
        logger.info("보관 기간이 지난 기록 %d건을 삭제했습니다.", result.rowcount)
    return result.rowcount
