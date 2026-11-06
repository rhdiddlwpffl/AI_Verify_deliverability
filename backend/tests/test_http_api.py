"""FastAPI TestClient로 HTTP 수준에서 확인한다: 오류 응답 형식, 상태 코드, CORS, 헤더, 접속 정보 비노출.
분류/검색/비교는 가짜(tests/fakes.py)를 끼우므로 외부 호출과 비용이 없다. db 마커 테스트만 실제 DB를 쓴다."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api.routes import analyses as route_module
from app.api.routes import health as health_module
from app.core.errors import AppError
from app.db.session import DatabaseNotConfiguredError, get_session
from app.main import app
from app.services import rate_limit
from tests.fakes import TEXT, patched

ORIGIN = "http://localhost:5173"
TOKEN = "a1b2c3d4" * 8  # 형식이 올바른 64자 16진수 토큰
# 가짜 값(조립해서 만든다: 접속 주소 모양 문자열을 소스에 그대로 두지 않는다)
SECRET = "postgresql" + "://user:FAKE-PASSWORD@db.example.com:5432/postgres"


@pytest.fixture
def client():
    # raise_server_exceptions=False: 서버 내부 오류도 실제 서버처럼 500 응답으로 받는다
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def error_of(response):
    body = response.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message"}, body  # 오류 형식이 항상 같다
    assert body["error"]["message"].strip()
    return body["error"]


# ------------------------------------------------------------ 기본 / 입력 오류


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200 and response.json()["status"] == "ok"


@pytest.mark.parametrize(
    ("kwargs", "status", "code"),
    [
        ({"json": {}}, 422, "invalid_request"),  # text 필드 없음
        ({"json": {"text": 123}}, 422, "invalid_request"),  # 잘못된 타입
        ({"json": {"text": "a" * 5001}}, 422, "input_too_long"),  # 글자 수 상한 초과
        ({"json": {"text": "   \n "}}, 422, "empty_input"),  # 공백만
        ({"json": {"text": "```\nx = 1\n```"}}, 422, "no_sentences"),  # 문장 없음
        ({"content": "{", "headers": {"content-type": "application/json"}}, 400, "invalid_json"),  # 깨진 JSON
    ],
)
def test_bad_input_gets_a_consistent_korean_error_and_never_reaches_the_limiter(client, kwargs, status, code):
    original = rate_limit.limiter
    rate_limit.limiter = None  # 잘못된 입력이 제한기/분석에 닿으면 AttributeError로 드러난다
    try:
        response = client.post("/analyses", **kwargs)
    finally:
        rate_limit.limiter = original
    assert response.status_code == status
    error = error_of(response)
    assert error["code"] == code
    assert any("가" <= ch <= "힣" for ch in error["message"])  # 사용자에게 보일 한국어 문장
    assert "aaaa" not in response.text  # 입력 원문을 응답에 되돌려 보내지 않는다


def test_framework_errors_are_translated_to_korean(client):
    not_found, wrong_method = client.get("/no-such-page"), client.get("/analyses/not-a-uuid")
    assert not_found.status_code == 404 and error_of(not_found)["message"] != "Not Found"
    assert any("가" <= ch <= "힣" for ch in error_of(not_found)["message"])
    assert client.put("/analyses").status_code == 405 and "Method Not Allowed" not in client.put("/analyses").text
    assert wrong_method.status_code in (401, 422)  # 토큰 검사나 UUID 검사에서 걸린다. 어느 쪽이든 같은 오류 형식이다
    error_of(wrong_method)


def test_unexpected_exception_becomes_a_generic_500_without_internal_details(client):
    def boom(text):
        raise RuntimeError(f"내부 버그 {SECRET}")

    with patched():
        original = route_module.analyze_text
        route_module.analyze_text = boom
        try:
            response = client.post("/analyses", json={"text": "에펠탑은 1889년에 지어졌다."})
        finally:
            route_module.analyze_text = original
    assert response.status_code == 500 and error_of(response)["code"] == "internal_error"
    assert "SUPER-SECRET" not in response.text and "RuntimeError" not in response.text


def test_internal_errors_still_carry_cors_headers_so_the_browser_can_show_the_message(client):
    """500 응답에 CORS 헤더가 없으면 브라우저는 서버 메시지 대신 '연결할 수 없음'만 보여 준다."""

    def boom(text):
        raise RuntimeError("버그")

    with patched():
        original = route_module.analyze_text
        route_module.analyze_text = boom
        try:
            response = client.post("/analyses", json={"text": "에펠탑은 1889년에 지어졌다."}, headers={"Origin": ORIGIN})
        finally:
            route_module.analyze_text = original
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == ORIGIN


# ------------------------------------------------------------ 정상 흐름 / 헤더 / 제한


def test_analysis_happy_path_over_http(client):
    with patched():
        response = client.post("/analyses", json={"text": TEXT})
    assert response.status_code == 200
    body = response.json()
    assert (body["sentence_count"], body["check_worthy_count"], body["save_status"]) == (3, 2, "not_requested")
    assert body["claims"][0]["verification_status"] == "supported"
    assert body["claims"][1]["verification_status"] == "search_failed"  # 검색 실패는 문장별로만 표시된다
    assert "에펠탑" in response.text  # 한글이 깨지지 않고 그대로 나온다


def test_malformed_token_header_is_rejected_before_any_analysis(client):
    called = []
    original = route_module.analyze_text
    route_module.analyze_text = lambda text: called.append(text)
    try:
        with patched():
            response = client.post("/analyses", json={"text": TEXT}, headers={"X-Anon-Token": "bad token!"})
    finally:
        route_module.analyze_text = original
    assert response.status_code == 400 and error_of(response)["code"] == "invalid_token" and called == []


def test_rate_limit_error_exposes_retry_after_to_the_browser(client):
    class DenyingLimiter:
        def analysis_slot(self):
            from contextlib import nullcontext

            return nullcontext()

        def admit_analysis(self, ip):
            raise AppError(429, "daily_limit_reached", "24시간 사용 횟수를 모두 사용했습니다.", {"Retry-After": "42"})

    original = rate_limit.limiter
    rate_limit.limiter = DenyingLimiter()
    try:
        response = client.post("/analyses", json={"text": TEXT}, headers={"Origin": ORIGIN})
    finally:
        rate_limit.limiter = original
    assert response.status_code == 429 and error_of(response)["code"] == "daily_limit_reached"
    assert response.headers["retry-after"] == "42"
    assert "retry-after" in response.headers.get("access-control-expose-headers", "").lower()  # 브라우저 스크립트가 읽을 수 있다


# ------------------------------------------------------------ 기록 API: 인증과 DB 오류


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/analyses"),
        ("GET", f"/analyses/{uuid.uuid4()}"),
        ("DELETE", f"/analyses/{uuid.uuid4()}"),
        ("DELETE", "/analyses"),
    ],
)
def test_history_endpoints_require_a_valid_token_before_touching_the_database(client, method, path):
    def must_not_open_a_session():
        raise AssertionError("토큰 검사보다 먼저 DB 세션을 열면 안 된다")

    app.dependency_overrides[get_session] = must_not_open_a_session
    no_token = client.request(method, path)
    assert no_token.status_code == 401 and error_of(no_token)["code"] == "missing_token"
    bad_token = client.request(method, path, headers={"X-Anon-Token": "short"})
    assert bad_token.status_code == 400 and error_of(bad_token)["code"] == "invalid_token"


def test_database_failure_returns_503_without_leaking_connection_details(client):
    def broken_session():
        raise OperationalError("select 1", {}, Exception(f"connection failed: {SECRET}"))

    app.dependency_overrides[get_session] = broken_session
    response = client.get("/analyses", headers={"X-Anon-Token": TOKEN})
    assert response.status_code == 503 and error_of(response)["code"] == "db_unavailable"
    assert "SUPER-SECRET" not in response.text and "postgresql" not in response.text


def test_database_not_configured_returns_503(client):
    def not_configured():
        raise DatabaseNotConfiguredError("no db")

    app.dependency_overrides[get_session] = not_configured
    response = client.get("/analyses", headers={"X-Anon-Token": TOKEN})
    assert response.status_code == 503 and error_of(response)["code"] == "db_not_configured"


@pytest.mark.parametrize(
    ("raised", "code"),
    [(DatabaseNotConfiguredError("x"), "db_not_configured"), (RuntimeError(f"접속 실패 {SECRET}"), "db_unavailable")],
)
def test_health_db_reports_failures_without_details(client, raised, code):
    def broken_engine():
        raise raised

    original = health_module.get_engine
    health_module.get_engine = broken_engine
    try:
        response = client.get("/health/db")
    finally:
        health_module.get_engine = original
    assert response.status_code == 503 and error_of(response)["code"] == code
    assert "SUPER-SECRET" not in response.text


# ------------------------------------------------------------ CORS


def test_cors_preflight_allows_our_frontend_only(client):
    allowed = client.options(
        "/analyses",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-anon-token"},
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "x-anon-token" in allowed.headers["access-control-allow-headers"].lower()

    delete = client.options(
        "/analyses/x", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "x-anon-token"}
    )
    assert "DELETE" in delete.headers["access-control-allow-methods"]

    denied = client.options("/analyses", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in denied.headers  # 허용하지 않은 주소에는 CORS 허용 헤더를 주지 않는다


# ------------------------------------------------------------ 실제 DB로 저장/조회/삭제 (db 마커)


@pytest.mark.db
def test_save_then_read_then_delete_over_http_with_the_real_database(client):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    headers = {"X-Anon-Token": token}
    try:
        with patched():
            saved = client.post("/analyses", json={"text": TEXT, "save": True}, headers=headers)
        assert saved.status_code == 200 and saved.json()["save_status"] == "saved"
        analysis_id = saved.json()["analysis_id"]

        listing = client.get("/analyses", headers=headers).json()
        assert [item["id"] for item in listing] == [analysis_id]

        detail = client.get(f"/analyses/{analysis_id}", headers=headers)
        assert detail.status_code == 200 and detail.json()["text"] == TEXT
        strip = lambda body: {k: v for k, v in body.items() if k not in ("save_status", "analysis_id")}  # noqa: E731
        assert strip(detail.json()["result"]) == strip(saved.json())  # 저장 후 읽은 결과가 방금 받은 응답과 같다

        other = {"X-Anon-Token": uuid.uuid4().hex + uuid.uuid4().hex}
        assert client.get(f"/analyses/{analysis_id}", headers=other).status_code == 404  # 남의 기록
        assert client.delete(f"/analyses/{analysis_id}", headers=other).status_code == 404

        assert client.delete(f"/analyses/{analysis_id}", headers=headers).json() == {"deleted": 1}
        assert client.get(f"/analyses/{analysis_id}", headers=headers).status_code == 404
        assert error_of(client.delete(f"/analyses/{analysis_id}", headers=headers))["code"] == "not_found"
    finally:
        client.delete("/analyses", headers=headers)  # 중간에 실패해도 시험 데이터를 남기지 않는다


@pytest.mark.db
def test_delete_all_over_http_and_health_db(client):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    headers = {"X-Anon-Token": token}
    try:
        with patched():
            for _ in range(2):
                assert client.post("/analyses", json={"text": TEXT, "save": True}, headers=headers).json()["save_status"] == "saved"
        assert client.delete("/analyses", headers=headers).json() == {"deleted": 2}
        assert client.get("/analyses", headers=headers).json() == []
        assert client.get("/health/db").json() == {"status": "ok", "database": "connected"}
    finally:
        client.delete("/analyses", headers=headers)
