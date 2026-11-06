import asyncio
import json
from types import SimpleNamespace

from sqlalchemy.exc import OperationalError

from app.api.routes import analyses as route_module
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import DatabaseNotConfiguredError
from app.schemas.analysis import AnalyzeRequest
from app.services import rate_limit
from app.services.rate_limit import RateLimiter, client_ip, ip_hash


def request(peer="10.0.0.1", xff=None):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer) if peer else None, headers=headers)


# ------------------------------------------------------------ client_ip


def test_client_ip_ignores_forwarded_header_when_no_proxy_is_trusted():
    assert client_ip(request("10.0.0.1", xff="6.6.6.6"), 0) == "10.0.0.1"  # 가짜 헤더로 IP를 바꿀 수 없다


def test_client_ip_uses_rightmost_entries_not_the_spoofable_leftmost():
    # 클라이언트가 'X-Forwarded-For: 6.6.6.6'을 보내면 프록시가 자기가 본 실제 주소를 오른쪽에 덧붙인다.
    assert client_ip(request(xff="6.6.6.6, 203.0.113.5"), 1) == "203.0.113.5"
    assert client_ip(request(xff="6.6.6.6, 203.0.113.5, 10.1.1.1"), 2) == "203.0.113.5"
    assert client_ip(request(xff="203.0.113.5"), 1) == "203.0.113.5"


def test_client_ip_falls_back_to_peer_when_header_is_unexpected():
    assert client_ip(request("10.0.0.1"), 1) == "10.0.0.1"  # 헤더 없음
    assert client_ip(request("10.0.0.1", xff="203.0.113.5"), 2) == "10.0.0.1"  # 기대보다 항목이 적음
    assert client_ip(request("10.0.0.1", xff="6.6.6.6, not-an-ip"), 1) == "10.0.0.1"  # IP가 아닌 값
    assert client_ip(request("10.0.0.1", xff=" , "), 1) == "10.0.0.1"
    assert client_ip(request(None), 0) == "unknown"  # 연결 정보 없음


def test_client_ip_normalizes_ipv6():
    assert client_ip(request(xff="x, 2001:DB8:0:0:0:0:0:1"), 1) == "2001:db8::1"


def test_ip_hash_is_salted_deterministic_and_hides_the_ip():
    a = ip_hash("203.0.113.5", "salt-one-salt-one")
    assert a == ip_hash("203.0.113.5", "salt-one-salt-one") and len(a) == 64
    assert a != ip_hash("203.0.113.5", "salt-two-salt-two")  # salt가 다르면 해시도 다르다
    assert a != ip_hash("203.0.113.6", "salt-one-salt-one")
    assert "203.0.113.5" not in a


# ------------------------------------------------------------ 제한기 (DB 없이: 메모리 카운터)


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


def broken_db():
    raise OperationalError("select 1", {}, Exception("db down"))


def make_limiter(clock=None, session_factory=broken_db, **overrides):
    params = dict(
        ip_per_minute=3,
        ip_per_day=20,
        global_per_day=60,
        history_per_minute=60,
        max_concurrent=3,
        salt="test-salt-test-salt",
        session_factory=session_factory,
        clock=clock or Clock(),
    )
    params.update(overrides)
    return RateLimiter(**params)


def expect_limit(fn, status, code):
    try:
        fn()
    except AppError as exc:
        assert (exc.status_code, exc.code) == (status, code), (exc.status_code, exc.code, exc.message)
        return exc
    raise AssertionError(f"AppError({status}, {code})가 나야 한다")


def test_minute_limit_blocks_then_recovers_and_is_per_ip():
    clock = Clock()
    limiter = make_limiter(clock, ip_per_minute=3)
    for _ in range(3):
        limiter.admit_analysis("1.1.1.1")
    exc = expect_limit(lambda: limiter.admit_analysis("1.1.1.1"), 429, "rate_limited")
    assert exc.headers["Retry-After"] == "60" and "1분 후 다시 시도" in exc.message
    limiter.admit_analysis("2.2.2.2")  # 다른 IP는 영향 없음
    clock.now += 61
    limiter.admit_analysis("1.1.1.1")  # 1분 뒤에는 다시 가능


def test_zero_limit_blocks_everything_without_crashing():
    # 실제 버그였다: 한도를 0으로 두면 빈 기록에서 첫 항목을 읽다가 IndexError(서버 오류)가 났다.
    expect_limit(lambda: make_limiter(ip_per_minute=0).admit_analysis("1.1.1.1"), 429, "rate_limited")
    expect_limit(lambda: make_limiter(ip_per_minute=100, ip_per_day=0).admit_analysis("1.1.1.1"), 429, "daily_limit_reached")
    expect_limit(lambda: make_limiter(ip_per_minute=100, global_per_day=0).admit_analysis("1.1.1.1"), 429, "service_daily_limit")
    expect_limit(lambda: make_limiter(history_per_minute=0).check_history("1.1.1.1"), 429, "rate_limited")


def test_per_ip_daily_limit_in_memory_fallback():
    clock = Clock()
    limiter = make_limiter(clock, ip_per_minute=100, ip_per_day=2)
    limiter.admit_analysis("1.1.1.1")
    limiter.admit_analysis("1.1.1.1")
    exc = expect_limit(lambda: limiter.admit_analysis("1.1.1.1"), 429, "daily_limit_reached")
    assert "2회" in exc.message and "24시간" in exc.message
    limiter.admit_analysis("2.2.2.2")
    clock.now += 24 * 3600 + 1
    limiter.admit_analysis("1.1.1.1")  # 24시간이 지나면 다시 가능


def test_global_daily_limit_applies_across_ips():
    limiter = make_limiter(global_per_day=3, ip_per_minute=100)
    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        limiter.admit_analysis(ip)
    exc = expect_limit(lambda: limiter.admit_analysis("4.4.4.4"), 429, "service_daily_limit")
    assert "하루 사용량 한도" in exc.message and int(exc.headers["Retry-After"]) > 0


def test_blocked_requests_do_not_consume_the_daily_quota():
    clock = Clock()
    limiter = make_limiter(clock, ip_per_minute=1, ip_per_day=2)
    limiter.admit_analysis("1.1.1.1")
    for _ in range(5):  # 분당 한도에 걸린 요청은 하루 횟수를 소모하지 않는다
        expect_limit(lambda: limiter.admit_analysis("1.1.1.1"), 429, "rate_limited")
    clock.now += 61
    limiter.admit_analysis("1.1.1.1")  # 하루 2회 중 두 번째. 소모되지 않았으니 가능
    clock.now += 61
    expect_limit(lambda: limiter.admit_analysis("1.1.1.1"), 429, "daily_limit_reached")


def test_database_not_configured_also_falls_back_to_memory():
    def not_configured():
        raise DatabaseNotConfiguredError("no db")

    limiter = make_limiter(session_factory=not_configured, ip_per_minute=100, ip_per_day=1)
    limiter.admit_analysis("1.1.1.1")
    expect_limit(lambda: limiter.admit_analysis("1.1.1.1"), 429, "daily_limit_reached")  # DB가 없어도 제한한다


def test_concurrency_slots():
    limiter = make_limiter(max_concurrent=2)
    with limiter.analysis_slot():
        with limiter.analysis_slot():
            exc = expect_limit(lambda: limiter.analysis_slot().__enter__(), 503, "busy")
            assert exc.headers["Retry-After"] == "10"
        with limiter.analysis_slot():  # 하나를 반납하면 다시 들어갈 수 있다
            pass


def test_slot_is_released_when_the_analysis_raises():
    limiter = make_limiter(max_concurrent=1)
    try:
        with limiter.analysis_slot():
            raise RuntimeError("분석 중 오류")
    except RuntimeError:
        pass
    with limiter.analysis_slot():  # 예외가 나도 슬롯이 새지 않는다
        pass


def test_history_limit():
    limiter = make_limiter(history_per_minute=2)
    limiter.check_history("1.1.1.1")
    limiter.check_history("1.1.1.1")
    expect_limit(lambda: limiter.check_history("1.1.1.1"), 429, "rate_limited")
    limiter.check_history("2.2.2.2")


def test_tracked_keys_are_capped():
    original = rate_limit._MAX_TRACKED_KEYS
    rate_limit._MAX_TRACKED_KEYS = 20
    try:
        limiter = make_limiter(ip_per_minute=1000, ip_per_day=1000, global_per_day=10_000)
        for i in range(200):
            limiter.admit_analysis(f"10.0.{i // 250}.{i % 250}")
        assert len(limiter._minute) <= 20 and len(limiter._day_ip) <= 20  # 공격으로 메모리가 무한히 늘지 않는다
    finally:
        rate_limit._MAX_TRACKED_KEYS = original


def test_app_error_headers_reach_the_http_response():
    from app.main import app

    exc = expect_limit(lambda: make_limiter(ip_per_minute=0).admit_analysis("1.1.1.1"), 429, "rate_limited")
    response = asyncio.run(app.exception_handlers[AppError](None, exc))
    assert response.status_code == 429 and int(response.headers["retry-after"]) >= 1
    assert json.loads(response.body)["error"]["code"] == "rate_limited"


# ------------------------------------------------------------ 설정 검증


def test_production_requires_a_real_salt():
    for bad in ("dev-only-salt-change-me", "short"):
        try:
            Settings(_env_file=None, app_env="production", rate_limit_salt=bad)
        except ValueError:
            continue
        raise AssertionError(f"production + salt={bad!r}는 시작되면 안 된다")
    Settings(_env_file=None, app_env="production", rate_limit_salt="a-long-random-secret-value")  # 통과
    Settings(_env_file=None, app_env="local")  # 로컬은 기본 salt로 충분


# ------------------------------------------------------------ 라우트 연결


class FakeLimiter:
    def __init__(self, admit_error=None, busy=False):
        self.calls = []
        self.admit_error = admit_error
        self.busy = busy

    def admit_analysis(self, ip):
        self.calls.append(("admit", ip))
        if self.admit_error:
            raise self.admit_error

    def analysis_slot(self):
        limiter = self

        class Slot:
            def __enter__(self):
                limiter.calls.append(("slot-enter",))
                if limiter.busy:
                    raise AppError(503, "busy", "붐빔", {"Retry-After": "10"})

            def __exit__(self, *exc):
                limiter.calls.append(("slot-exit",))

        return Slot()


def run_route(text, limiter, analyze_called):
    original = (rate_limit.limiter, route_module.analyze_text)
    rate_limit.limiter = limiter
    route_module.analyze_text = lambda t: analyze_called.append(t) or (_ for _ in ()).throw(RuntimeError("stop"))
    try:
        route_module.create_analysis(AnalyzeRequest(text=text), request("203.0.113.9"), None)
    except (AppError, RuntimeError) as exc:
        return exc
    finally:
        rate_limit.limiter, route_module.analyze_text = original
    return None


def test_invalid_input_never_touches_the_limiter():
    for bad in ("   \n ", "```\nx\n```"):
        limiter, called = FakeLimiter(), []
        exc = run_route(bad, limiter, called)
        assert isinstance(exc, AppError) and exc.code in ("empty_input", "no_sentences")
        assert limiter.calls == [] and called == []  # 잘못된 입력은 사용 횟수를 소모하지 않는다


def test_limit_exceeded_stops_before_any_analysis():
    limiter, called = FakeLimiter(admit_error=AppError(429, "rate_limited", "x")), []
    exc = run_route("에펠탑은 1889년에 지어졌다.", limiter, called)
    assert isinstance(exc, AppError) and exc.code == "rate_limited"
    assert called == []  # 비용이 드는 분석은 시작되지 않는다
    assert limiter.calls == [("slot-enter",), ("admit", "203.0.113.9"), ("slot-exit",)]  # 슬롯은 반납된다


def test_busy_server_stops_before_counting_usage():
    limiter, called = FakeLimiter(busy=True), []
    exc = run_route("에펠탑은 1889년에 지어졌다.", limiter, called)
    assert isinstance(exc, AppError) and exc.code == "busy"
    assert called == [] and ("admit", "203.0.113.9") not in limiter.calls  # 못 들어온 요청은 횟수를 소모하지 않는다


def test_admitted_request_runs_the_analysis_inside_the_slot():
    limiter, called = FakeLimiter(), []
    exc = run_route("에펠탑은 1889년에 지어졌다.", limiter, called)
    assert isinstance(exc, RuntimeError)  # 가짜 분석이 호출되어 중단됨
    assert called == ["에펠탑은 1889년에 지어졌다."]
    assert limiter.calls == [("slot-enter",), ("admit", "203.0.113.9"), ("slot-exit",)]
