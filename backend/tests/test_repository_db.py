"""저장소 통합 테스트: 실제 DB(DATABASE_URL)에 연결해서 확인한다.
각 테스트는 바깥 트랜잭션 안에서 실행하고 끝에 롤백하므로 DB에 데이터가 남지 않는다.
DATABASE_URL이 없으면 건너뛴다."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, update
from sqlmodel import Session, select

from app.models import Analysis, Claim, Source
from app.services import repository
from app.services.result_data import ClaimData, ResultData, SourceData

TEXT = "에펠탑은 1889년에 지어졌다. 이 문장은 검색이 실패한다. 정말 멋지다. 비교가 실패한 문장이다. 없는 문장이다. 건너뛴 문장이다."


pytestmark = pytest.mark.db


@contextmanager
def db_session():
    from app.db.session import get_engine

    conn = get_engine().connect()
    outer = conn.begin()
    # commit()을 호출해도 SAVEPOINT만 풀리고, 바깥 트랜잭션은 마지막에 롤백된다.
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


def token_hash():
    return uuid4().hex + uuid4().hex  # 64자. 테스트마다 다른 사용자


def src(title, lang="ko", stance="neutral", quote="", downgraded=False, path=None):
    path = path or title
    return SourceData(
        title=title,
        url=f"https://{lang}.wikipedia.org/wiki/{path}",
        snippet=f"{title} 문서의 도입부 본문이다. 1889년에 건설되었다.",
        source=f"wikipedia-{lang}",
        stance=stance,
        quote=quote,
        downgraded=downgraded,
    )


def claim(idx, **kw):
    base = dict(
        idx=idx,
        text=f"문장 {idx}",
        start=idx * 10,
        end=idx * 10 + 5,
        claim_type="factual",
        check_worthy=True,
        flags=[],
        reason="이유",
        search_status="found",
        search_query="에펠탑",
        search_error=None,
        sources=[],
        verification_status="insufficient",
        verification_confidence="low",
        verification_rationale=None,
        verification_error=None,
    )
    base.update(kw)
    return ClaimData(**base)


def sample_data():
    """저장/복원이 까다로운 모든 상태를 한 번에 담은 결과."""
    quote = "1889년에 건설되었다."
    return ResultData(
        model="classify-model",
        model_info={"classification_model": "classify-model", "judge_model": "judge-model", "tokens": {"judge": {"input": 1, "output": 2}}},
        claims=[
            # 0: 찾음 + 비교 성공 (근거 / 제외된 근거 / 관련 없음)
            claim(
                0,
                flags=["contains_number", "contains_year"],
                sources=[
                    src("에펠탑", stance="supports", quote=quote),
                    src("귀스타브 에펠", stance="neutral", downgraded=True),
                    src("Eiffel Tower", lang="en", path="Eiffel_Tower"),
                ],
                verification_status="supported",
                verification_confidence="medium",
                verification_rationale="발췌문에서 건설 연도가 확인됨",
            ),
            # 1: 검색 실패
            claim(1, search_status="failed", search_error="unavailable", verification_status="search_failed", verification_confidence=None, verification_error="unavailable"),
            # 2: 확인 대상 아님 (취약점 신호는 가공하지 않은 값 그대로 저장된다)
            claim(2, claim_type="opinion", check_worthy=False, flags=["absolute_expression"], search_status="not_searched", search_query="", verification_status="not_checkable", verification_confidence=None),
            # 3: 찾았지만 비교 실패 → 출처별 stance가 None
            claim(
                3,
                sources=[src("에펠탑", stance=None), src("파리", stance=None)],
                verification_status="unverified",
                verification_confidence=None,
                verification_error="judge_failed",
            ),
            # 4: 찾지 못함
            claim(4, search_status="none", search_query="없는검색어", verification_status="insufficient", verification_confidence=None),
            # 5: 개수 제한으로 건너뜀
            claim(5, search_status="skipped", verification_status="unverified", verification_confidence=None, verification_error="skipped"),
        ],
    )


def count(session, model, *conditions):
    return session.exec(select(func.count()).select_from(model).where(*conditions)).one()


def test_roundtrip_restores_exactly_what_was_saved():
    with db_session() as session:
        h, data = token_hash(), sample_data()
        analysis_id = repository.save_analysis(session, h, TEXT, data)
        session.commit()

        stored = repository.load_analysis(session, h, analysis_id)
        assert stored is not None and stored.text == TEXT and stored.id == analysis_id
        assert stored.data.model == "classify-model"
        assert stored.data.model_info == data.model_info
        assert len(stored.data.claims) == len(data.claims)
        for original, restored in zip(data.claims, stored.data.claims, strict=True):
            assert restored == original, f"문장 {original.idx} 복원 불일치"


def test_other_users_cannot_read_or_delete():
    with db_session() as session:
        mine, other = token_hash(), token_hash()
        analysis_id = repository.save_analysis(session, mine, TEXT, sample_data())
        session.commit()

        assert repository.load_analysis(session, other, analysis_id) is None  # 남의 기록은 '없음'
        assert repository.delete_analysis(session, other, analysis_id) is False
        assert repository.list_analyses(session, other, 50) == []
        assert repository.delete_all(session, other) == 0
        assert repository.load_analysis(session, mine, analysis_id) is not None  # 내 기록은 그대로


def test_list_is_newest_first_with_counts_and_preview():
    with db_session() as session:
        h = token_hash()
        first = repository.save_analysis(session, h, "첫 번째 입력입니다.\n\n" + "가" * 200, sample_data())
        second = repository.save_analysis(session, h, TEXT, sample_data())
        session.commit()

        items = repository.list_analyses(session, h, 50)
        assert [i.id for i in items] == [second, first]  # 최신순
        newest = items[0]
        assert newest.sentence_count == 6 and newest.check_worthy_count == 5
        # not_checkable은 요약에서 빠지고, 나머지는 문장 수대로 센다
        assert newest.status_counts == {"supported": 1, "search_failed": 1, "unverified": 2, "insufficient": 1}
        assert items[1].preview.startswith("첫 번째 입력입니다.") and items[1].preview.endswith("…")
        assert len(items[1].preview) <= 81
        assert len(repository.list_analyses(session, h, 1)) == 1  # limit


def test_same_source_url_is_shared_and_upserted():
    with db_session() as session:
        h = token_hash()
        url_path = f"공유테스트-{uuid4().hex[:8]}"
        a = sample_data()
        a.claims[0].sources[0] = src("옛 제목", path=url_path)
        b = sample_data()
        b.claims[0].sources[0] = src("새 제목", path=url_path)
        repository.save_analysis(session, h, TEXT, a)
        repository.save_analysis(session, h, TEXT, b)
        session.commit()

        url = f"https://ko.wikipedia.org/wiki/{url_path}"
        assert count(session, Source, Source.url == url) == 1  # 같은 URL은 한 행
        assert session.exec(select(Source.title).where(Source.url == url)).one() == "새 제목"  # 제목은 갱신


def test_delete_cascades_and_keeps_shared_sources():
    with db_session() as session:
        h = token_hash()
        shared, unique = f"공유-{uuid4().hex[:8]}", f"단독-{uuid4().hex[:8]}"
        a, b = sample_data(), sample_data()
        a.claims[0].sources = [src("공유", path=shared), src("단독", path=unique)]
        b.claims[0].sources = [src("공유", path=shared)]
        id_a = repository.save_analysis(session, h, TEXT, a)
        id_b = repository.save_analysis(session, h, TEXT, b)
        session.commit()

        assert repository.delete_analysis(session, h, id_a) is True
        session.commit()

        assert count(session, Claim, Claim.analysis_id == id_a) == 0  # 하위 데이터가 함께 지워짐
        claim_ids_a = [c for c in session.exec(select(Claim.id).where(Claim.analysis_id == id_a))]
        assert claim_ids_a == []
        assert count(session, Source, Source.url == f"https://ko.wikipedia.org/wiki/{unique}") == 0  # 고아 출처 정리
        assert count(session, Source, Source.url == f"https://ko.wikipedia.org/wiki/{shared}") == 1  # 공유 출처는 유지
        assert repository.load_analysis(session, h, id_b) is not None  # 다른 기록은 영향 없음
        assert repository.delete_analysis(session, h, id_a) is False  # 두 번 지우면 없음


def test_delete_all_removes_only_my_analyses():
    with db_session() as session:
        mine, other = token_hash(), token_hash()
        repository.save_analysis(session, mine, TEXT, sample_data())
        repository.save_analysis(session, mine, TEXT, sample_data())
        keep = repository.save_analysis(session, other, TEXT, sample_data())
        session.commit()

        assert repository.delete_all(session, mine) == 2
        session.commit()
        assert repository.list_analyses(session, mine, 50) == []
        assert repository.load_analysis(session, other, keep) is not None


def test_cleanup_expired_respects_retention_and_zero_disables():
    with db_session() as session:
        h = token_hash()
        old = repository.save_analysis(session, h, TEXT, sample_data())
        recent = repository.save_analysis(session, h, TEXT, sample_data())
        session.exec(update(Analysis).where(Analysis.id == old).values(created_at=datetime.now(UTC) - timedelta(days=31)))
        session.commit()

        assert repository.cleanup_expired(session, 0) == 0  # 0이면 자동 삭제 안 함
        assert repository.load_analysis(session, h, old) is not None

        assert repository.cleanup_expired(session, 30) >= 1
        session.commit()
        assert repository.load_analysis(session, h, old) is None  # 31일 지난 기록은 삭제
        assert repository.load_analysis(session, h, recent) is not None  # 최근 기록은 유지


def test_empty_analysis_roundtrip():
    with db_session() as session:
        h = token_hash()
        empty = ResultData(claims=[], model="m", model_info={"classification_model": "m"})
        analysis_id = repository.save_analysis(session, h, "내용", empty)
        session.commit()
        stored = repository.load_analysis(session, h, analysis_id)
        assert stored is not None and stored.data.claims == []
        assert repository.list_analyses(session, h, 50)[0].sentence_count == 0
