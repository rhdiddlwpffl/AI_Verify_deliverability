"""24시간 사용 횟수 제한의 DB 부분을 실제 DB로 확인하는 통합 테스트. DATABASE_URL이 없으면 건너뛴다.
대부분은 바깥 트랜잭션을 롤백하므로 DB에 데이터가 남지 않는다. (동시성 테스트만 실제로 커밋하고 직접 지운다)"""

import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import AppError
from app.models import UsageEvent
from app.services.rate_limit import RateLimiter

SALT = "test-salt-test-salt"


class Borrowed:
    """이미 열려 있는 세션을 빌려 준다. (with 블록이 끝나도 세션을 닫지 않는다)"""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, *exc):
        return False


@contextmanager
def db_session():
    from app.db.session import get_engine

    conn = get_engine().connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


def make_limiter(session, **overrides):
    params = dict(
        ip_per_minute=1000,
        ip_per_day=20,
        global_per_day=60,
        history_per_minute=60,
        max_concurrent=3,
        salt=SALT,
        session_factory=lambda: Borrowed(session),
    )
    params.update(overrides)
    return RateLimiter(**params)


def expect_limit(fn, code):
    try:
        fn()
    except AppError as exc:
        assert (exc.status_code, exc.code) == (429, code), (exc.code, exc.message)
        return exc
    raise AssertionError(f"AppError(429, {code})가 나야 한다")


def count(session, *conditions):
    return session.exec(select(func.count()).select_from(UsageEvent).where(*conditions)).one()


def skip():
    return not settings.database_url


def test_per_ip_daily_limit_is_enforced_by_the_database():
    if skip():
        return
    with db_session() as session:
        limiter = make_limiter(session, ip_per_day=2)
        key = limiter.ip_hash("203.0.113.5")
        limiter.admit_analysis("203.0.113.5")
        limiter.admit_analysis("203.0.113.5")
        exc = expect_limit(lambda: limiter.admit_analysis("203.0.113.5"), "daily_limit_reached")
        assert 0 < int(exc.headers["Retry-After"]) <= 86400
        assert count(session, UsageEvent.ip_hash == key) == 2  # 거절된 요청은 기록하지 않는다
        limiter.admit_analysis("203.0.113.6")  # 다른 IP는 영향 없음


def test_global_daily_limit_is_enforced_by_the_database():
    if skip():
        return
    with db_session() as session:
        before = count(session)
        limiter = make_limiter(session, global_per_day=before + 3)
        for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
            limiter.admit_analysis(ip)
        expect_limit(lambda: limiter.admit_analysis("4.4.4.4"), "service_daily_limit")


def test_limit_survives_a_server_restart():
    """서버가 재시작/절전에서 깨어나 메모리가 초기화돼도 DB 기록으로 계속 제한한다. (이 설계의 핵심 이유)"""
    if skip():
        return
    with db_session() as session:
        first_run = make_limiter(session, ip_per_day=2)
        first_run.admit_analysis("203.0.113.5")
        first_run.admit_analysis("203.0.113.5")

        after_restart = make_limiter(session, ip_per_day=2)  # 메모리 카운터가 비어 있는 새 제한기
        assert not after_restart._day_ip and not after_restart._day_global
        expect_limit(lambda: after_restart.admit_analysis("203.0.113.5"), "daily_limit_reached")


def test_events_older_than_24_hours_do_not_count_and_old_ones_are_purged():
    if skip():
        return
    with db_session() as session:
        limiter = make_limiter(session, ip_per_day=1)
        key = limiter.ip_hash("203.0.113.5")
        now = datetime.now(UTC)
        stale = UsageEvent(ip_hash=key, created_at=now - timedelta(hours=25))  # 24시간 창 밖, 보관 기간 안
        expired = UsageEvent(ip_hash=key, created_at=now - timedelta(days=3))  # 보관 기간(2일) 밖
        session.add_all([stale, expired])
        session.flush()

        limiter.admit_analysis("203.0.113.5")  # 25시간 전 기록은 세지 않으므로 통과
        remaining = {e.id for e in session.exec(select(UsageEvent).where(UsageEvent.ip_hash == key))}
        assert expired.id not in remaining  # 이틀이 지난 기록은 정리된다
        assert stale.id in remaining  # 25시간 전 기록은 아직 보관된다
        expect_limit(lambda: limiter.admit_analysis("203.0.113.5"), "daily_limit_reached")


def test_zero_limits_block_in_the_database_path_too():
    if skip():
        return
    with db_session() as session:
        expect_limit(lambda: make_limiter(session, ip_per_day=0).admit_analysis("1.1.1.1"), "daily_limit_reached")
        expect_limit(lambda: make_limiter(session, global_per_day=0).admit_analysis("1.1.1.1"), "service_daily_limit")


def test_raw_ip_is_never_stored():
    if skip():
        return
    with db_session() as session:
        limiter = make_limiter(session)
        limiter.admit_analysis("203.0.113.5")
        stored = session.exec(select(UsageEvent.ip_hash).where(UsageEvent.ip_hash == limiter.ip_hash("203.0.113.5"))).one()
        assert len(stored) == 64 and "203.0.113.5" not in stored
        assert count(session, UsageEvent.ip_hash == "203.0.113.5") == 0


def test_concurrent_requests_cannot_exceed_the_limit():
    """동시에 들어온 요청들이 '아직 한도 안'이라고 함께 판단해서 한도를 넘는 일이 없어야 한다.
    (확인과 기록을 DB 락으로 한 번에 하나씩 처리하기 때문에 정확히 한도만큼만 통과한다)
    이 테스트만 실제로 커밋하므로, 끝에 직접 지운다."""
    if skip():
        return
    from app.db.session import get_engine

    limit, attempts = 4, 10
    limiter = RateLimiter(
        ip_per_minute=1000,
        ip_per_day=limit,
        global_per_day=100_000,
        history_per_minute=60,
        max_concurrent=3,
        salt=SALT + str(time.time()),  # 이 테스트만의 IP 해시를 쓴다
        session_factory=lambda: Session(get_engine()),
    )
    key = limiter.ip_hash("203.0.113.77")
    results: list[str] = []
    lock = threading.Lock()
    start = threading.Barrier(attempts)

    def attempt():
        start.wait()  # 모든 스레드가 동시에 출발
        try:
            limiter.admit_analysis("203.0.113.77")
            outcome = "ok"
        except AppError as exc:
            outcome = exc.code
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=attempt) for _ in range(attempts)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert results.count("ok") == limit, results
        assert results.count("daily_limit_reached") == attempts - limit, results
        with Session(get_engine()) as session:
            assert count(session, UsageEvent.ip_hash == key) == limit
    finally:
        with Session(get_engine()) as session:
            session.exec(delete(UsageEvent).where(UsageEvent.ip_hash == key))
            session.commit()
