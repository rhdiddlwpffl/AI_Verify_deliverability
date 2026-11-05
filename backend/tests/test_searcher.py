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


def make_provider(fetch, sleeps=None):
    return WikipediaProvider(
        fetch=fetch,
        user_agent="TestAgent/1.0 (test)",
        results=3,
        extract_chars=400,
        sleep=(sleeps.append if sleeps is not None else (lambda _: None)),
    )


def test_detect_language():
    assert detect_language("에펠탑") == "ko"
    assert detect_language("Eiffel Tower 1889") == "en"
    assert detect_language("ㅋㅋ") == "ko"


def test_parses_sorts_and_cleans_results():
    provider = make_provider(lambda url, params, headers, timeout: json_response(PAGES_RESPONSE))
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


def test_retries_once_on_429_then_succeeds():
    calls = []

    def fetch(url, params, headers, timeout):
        calls.append(1)
        if len(calls) == 1:
            return HttpResponse(429, {"retry-after": "2"}, b"")
        return json_response(PAGES_RESPONSE)

    sleeps: list[float] = []
    results = make_provider(fetch, sleeps).search("에펠탑")
    assert len(calls) == 2 and len(results) == 2
    assert sleeps == [2.0]  # Retry-After를 따른다


def test_retry_after_is_capped_and_garbage_is_ignored():
    sleeps: list[float] = []
    provider = make_provider(lambda *a: HttpResponse(429, {"retry-after": "999"}, b""), sleeps)
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        pass
    assert sleeps == [5.0]

    sleeps = []
    provider = make_provider(lambda *a: HttpResponse(429, {"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}, b""), sleeps)
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        pass
    assert sleeps == [1.0]


def test_rate_limited_after_retries():
    provider = make_provider(lambda *a: HttpResponse(429, {}, b""))
    try:
        provider.search("에펠탑")
    except SearchRateLimitedError:
        return
    raise AssertionError("SearchRateLimitedError가 나야 한다")


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
