from app.services.searcher import (
    HttpResponse,
    SearchBadResponseError,
    SearchRateLimitedError,
    SearchUnavailableError,
    WikipediaProvider,
    detect_language,
)

PAGES_RESPONSE = {
    "query": {
        "pages": [
            # 일부러 index 순서를 뒤섞어서 정렬되는지 본다
            {"pageid": 2, "title": "귀스타브 에펠", "index": 2, "extract": "프랑스의  건축가이다.\n구조 공학자."},
            {"pageid": 1, "title": "에펠탑 (파리)", "index": 1, "extract": "에펠탑은 1889년에 지어졌다."},
            {"pageid": 3, "title": "본문 없음", "index": 3, "extract": ""},
        ]
    }
}


def json_response(data, status=200, headers=None):
    import json

    return HttpResponse(status, headers or {}, json.dumps(data).encode("utf-8"))


class FakeTime:
    """가짜 시계. sleep을 호출하면 기다리는 대신 시계를 그만큼 앞으로 돌리고, 기다린 시간을 기록한다."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_provider(fetch, ft=None, **overrides):
    ft = ft or FakeTime()
    params = dict(
        fetch=fetch,
        user_agent="TestAgent/1.0 (test)",
        results=3,
        extract_chars=400,
        sleep=ft.sleep,
        clock=ft.clock,
        burst=100,  # 속도 조절을 보는 테스트가 아니면 걸리지 않게 넉넉히
        refill_per_second=100.0,
        max_wait=10.0,
        cache_ttl=0,  # 캐시를 보는 테스트가 아니면 끈다
        cache_max_entries=100,
    )
    params.update(overrides)
    return WikipediaProvider(**params)


def ok_fetch(calls=None):
    def fetch(url, params, headers, timeout):
        if calls is not None:
            calls.append(params["gsrsearch"])
        return json_response(PAGES_RESPONSE)

    return fetch


def test_detect_language():
    assert detect_language("에펠탑") == "ko"
    assert detect_language("Eiffel Tower 1889") == "en"
    assert detect_language("ㅋㅋ") == "ko"


def test_parses_sorts_and_cleans_results():
    provider = make_provider(ok_fetch())
    results = provider.search("에펠탑")
    assert [r.title for r in results] == ["에펠탑 (파리)", "귀스타브 에펠"]  # index 순, 본문 없는 문서 제외
    assert results[1].snippet == "프랑스의 건축가이다. 구조 공학자."  # 공백/줄바꿈 정리
    assert results[0].url == "https://ko.wikipedia.org/wiki/%EC%97%90%ED%8E%A0%ED%83%91_(%ED%8C%8C%EB%A6%AC)"
    assert results[0].source == "wikipedia-ko"


def test_invisible_characters_are_removed_from_snippets():
    data = {"query": {"pages": [{"title": "t", "index": 1, "extract": "발음: \u200b[tuʁ]\ufeff 에\u2060펠"}]}}
    results = make_provider(lambda *a: json_response(data)).search("에펠탑")
    assert results[0].snippet == "발음: [tuʁ] 에펠"


def test_request_uses_language_host_user_agent_and_params():
    seen = []

    def fetch(url, params, headers, timeout):
        seen.append((url, params, headers, timeout))
        return json_response({"batchcomplete": True})

    provider = make_provider(fetch)
    assert provider.search("Eiffel Tower") == []
    assert provider.search("에펠탑") == []
    assert seen[0][0].startswith("https://en.wikipedia.org/") and seen[1][0].startswith("https://ko.wikipedia.org/")
    assert seen[0][2]["User-Agent"] == "TestAgent/1.0 (test)"
    assert seen[0][3] > 0  # 시간 제한이 항상 붙는다
    params = seen[0][1]
    assert params["gsrsearch"] == "Eiffel Tower" and params["gsrnamespace"] == 0
    assert params["exintro"] == 1 and params["explaintext"] == 1 and params["exchars"] == 400


def test_empty_query_makes_no_request():
    def fetch(url, params, headers, timeout):
        raise AssertionError("요청이 나가면 안 된다")

    assert make_provider(fetch).search("   ") == []


def test_long_query_is_truncated_and_whitespace_collapsed():
    seen = []

    def fetch(url, params, headers, timeout):
        seen.append(params["gsrsearch"])
        return json_response({})

    make_provider(fetch).search("가  나\n다 " + "a" * 500)
    assert seen[0].startswith("가 나 다 a") and len(seen[0]) == 200


# ------------------------------------------------------------ 429: 쿨다운


def test_short_retry_after_is_waited_out_then_succeeds():
    calls = []

    def fetch(url, params, headers, timeout):
        calls.append(1)
        if len(calls) == 1:
            return HttpResponse(429, {"retry-after": "2"}, b"")
        return json_response(PAGES_RESPONSE)

    ft = FakeTime()
    results = make_provider(fetch, ft).search("에펠탑")
    assert len(calls) == 2 and len(results) == 2
    assert ft.sleeps == [2.0]  # Retry-After만큼 기다린 뒤 한 번 더 시도한다


def test_long_retry_after_fails_fast_without_hammering_the_server():
    """실측: 걸린 채로 계속 요청하면 대기 시간이 늘어난다. 그래서 쿨다운이 길면 요청을 보내지 않는다."""
    calls = []

    def fetch(url, params, headers, timeout):
        calls.append(params["gsrsearch"])
        return HttpResponse(429, {"retry-after": "30"}, b"")

    ft = FakeTime()
    provider = make_provider(fetch, ft)  # max_wait=10초
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        pass
    else:
        raise AssertionError("SearchRateLimitedError가 나야 한다")
    assert calls == ["에펠탑"] and ft.sleeps == []  # 한 번만 보냈고 기다리지도 않았다

    for query in ("파이썬", "훈민정음", "서울"):  # 쿨다운 중에는 다른 검색어도 요청 자체를 보내지 않는다
        try:
            provider.search(query)
        except SearchRateLimitedError:
            continue
        raise AssertionError("쿨다운 중에는 실패해야 한다")
    assert calls == ["에펠탑"]

    ft.now += 31  # 쿨다운이 끝나면 다시 보낸다
    ok_calls = []
    provider._fetch = ok_fetch(ok_calls)
    assert provider.search("파이썬") and ok_calls == ["파이썬"]


def test_huge_retry_after_is_capped_and_garbage_uses_default():
    ft = FakeTime()
    provider = make_provider(lambda *a: HttpResponse(429, {"retry-after": "999999"}, b""), ft)
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        pass
    assert provider._throttle._blocked_until - ft.now <= 120.0  # 서버가 아무리 길게 말해도 120초까지만 쉰다

    ft = FakeTime()
    provider = make_provider(lambda *a: HttpResponse(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, b""), ft)
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        pass
    assert ft.sleeps == [5.0]  # 숫자가 아니면 기본 5초 쿨다운 후 재시도


def test_rate_limited_error_after_two_attempts():
    provider = make_provider(lambda *a: HttpResponse(429, {}, b""))
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        return
    raise AssertionError("SearchRateLimitedError가 나야 한다")


# ------------------------------------------------------------ 속도 조절 (토큰 버킷)


def test_requests_beyond_the_burst_are_spaced_out():
    calls = []
    ft = FakeTime()
    provider = make_provider(ok_fetch(calls), ft, burst=2, refill_per_second=0.5)
    for q in ("가", "나", "다", "라"):
        provider.search(q)
    assert len(calls) == 4
    assert ft.sleeps == [2.0, 2.0]  # 처음 2개는 바로, 3번째와 4번째는 토큰이 찰 때까지(0.5/초 → 2초) 기다린다


def test_waiting_too_long_for_a_token_fails_without_a_request():
    calls = []
    ft = FakeTime()
    provider = make_provider(ok_fetch(calls), ft, burst=1, refill_per_second=0.1, max_wait=5.0)
    provider.search("가")
    try:
        provider.search("나")  # 토큰이 차려면 10초 → max_wait(5초)보다 길다
    except SearchRateLimitedError:
        pass
    else:
        raise AssertionError("기다릴 수 없으면 SearchRateLimitedError여야 한다")
    assert calls == ["가"] and ft.sleeps == []


def test_tokens_refill_over_time():
    ft = FakeTime()
    provider = make_provider(ok_fetch(), ft, burst=1, refill_per_second=0.1, max_wait=5.0)
    provider.search("가")
    ft.now += 10  # 10초 지나면 토큰 1개가 찬다
    provider.search("나")  # 기다림 없이 통과
    assert ft.sleeps == []


# ------------------------------------------------------------ 결과 캐시


def test_same_query_is_fetched_once_while_cached():
    calls = []
    provider = make_provider(ok_fetch(calls), cache_ttl=3600)
    first = provider.search("에펠탑")
    assert provider.search("에펠탑") == first
    assert provider.search("  에펠탑 \n") == first  # 공백이 달라도 같은 검색어
    assert calls == ["에펠탑"]


def test_cache_expires_and_is_per_language():
    calls = []
    ft = FakeTime()
    provider = make_provider(ok_fetch(calls), ft, cache_ttl=100)
    provider.search("에펠탑")
    provider.search("Eiffel Tower")  # 언어가 다르면 다른 항목
    assert calls == ["에펠탑", "Eiffel Tower"]
    ft.now += 101
    provider.search("에펠탑")
    assert calls == ["에펠탑", "Eiffel Tower", "에펠탑"]  # 시간이 지나면 다시 가져온다


def test_cache_evicts_least_recently_used_and_returns_copies():
    calls = []
    provider = make_provider(ok_fetch(calls), cache_ttl=3600, cache_max_entries=2)
    provider.search("가")
    provider.search("나")
    provider.search("가")  # '가'를 최근에 썼다
    provider.search("다")  # 가장 오래 안 쓴 '나'가 밀려난다
    calls.clear()
    provider.search("가")
    provider.search("다")
    assert calls == []  # 둘 다 캐시에 있다
    provider.search("나")
    assert calls == ["나"]  # 밀려난 것은 다시 가져온다

    result = provider.search("가")
    result.clear()  # 호출한 쪽이 목록을 고쳐도 캐시는 영향을 받지 않는다
    assert len(provider.search("가")) == 2


def test_failures_are_not_cached():
    calls = []

    def fetch(url, params, headers, timeout):
        calls.append(1)
        return HttpResponse(503, {}, b"") if len(calls) <= 2 else json_response(PAGES_RESPONSE)

    provider = make_provider(fetch, cache_ttl=3600)
    try:
        provider.search("에펠탑")
    except SearchUnavailableError:
        pass
    assert len(provider.search("에펠탑")) == 2  # 실패는 기억하지 않고 다시 시도해서 성공한다


# ------------------------------------------------------------ 그 밖의 오류


def test_server_error_becomes_unavailable():
    calls = []

    def fetch(url, params, headers, timeout):
        calls.append(1)
        return HttpResponse(503, {}, b"")

    try:
        make_provider(fetch).search("에펠탑")
    except SearchUnavailableError:
        assert len(calls) == 2  # 재시도 1회
        return
    raise AssertionError("SearchUnavailableError가 나야 한다")


def test_timeout_and_connection_errors_become_unavailable():
    for exc in (TimeoutError("timeout"), ConnectionResetError("reset"), OSError("network down")):
        calls = []

        def fetch(url, params, headers, timeout, exc=exc):
            calls.append(1)
            raise exc

        try:
            make_provider(fetch).search("에펠탑")
        except SearchUnavailableError:
            assert len(calls) == 2
            continue
        raise AssertionError(f"SearchUnavailableError가 나야 한다: {exc!r}")


def test_forbidden_is_not_retried():
    calls = []

    def fetch(url, params, headers, timeout):
        calls.append(1)
        return HttpResponse(403, {}, b"Please respect our robot policy")

    try:
        make_provider(fetch).search("에펠탑")
    except SearchBadResponseError:
        assert len(calls) == 1  # 차단은 재시도해도 소용없다
        return
    raise AssertionError("SearchBadResponseError가 나야 한다")


def test_api_error_codes():
    provider = make_provider(lambda *a: json_response({"error": {"code": "ratelimited"}}))
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        pass
    else:
        raise AssertionError("ratelimited는 SearchRateLimitedError여야 한다")

    provider = make_provider(lambda *a: json_response({"error": {"code": "badvalue"}}))
    try:
        provider.search("에펠탑")
    except SearchBadResponseError:
        return
    raise AssertionError("그 밖의 오류 코드는 SearchBadResponseError여야 한다")


def test_malformed_responses():
    bodies = (
        HttpResponse(200, {}, b"<html>not json</html>"),
        HttpResponse(200, {}, b"\xff\xfe invalid utf-8"),
        json_response(["not", "a", "dict"]),
        json_response({"query": {"pages": "oops"}}),
    )
    for response in bodies:
        try:
            make_provider(lambda *a, r=response: r).search("에펠탑")
        except SearchBadResponseError:
            continue
        raise AssertionError("SearchBadResponseError가 나야 한다")
