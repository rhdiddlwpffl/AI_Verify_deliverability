import json
import threading
import unicodedata
from contextlib import contextmanager

import anthropic
import httpx2

from app.core.config import settings
from app.services.searcher import SearchResult
from app.services.verifier import (
    SourceVerdict,
    derive_status,
    find_quote,
    judge_claims,
    parse_and_verify,
)

SNIPPET_A = "에펠탑은 프랑스 파리에 있는 격자형 철골 타워이다. 1889년에 파리 만국 박람회를 위해 건설되었다."
SNIPPET_B = "귀스타브 에펠은 프랑스의 건축가이자 구조 공학자이다. 에펠탑의 설계에 참여했다."


def result(title, snippet):
    return SearchResult(title, f"https://ko.wikipedia.org/wiki/{title}", snippet, "wikipedia-ko")


ITEMS = [(0, "에펠탑은 1889년에 지어졌다.", [result("에펠탑", SNIPPET_A), result("귀스타브 에펠", SNIPPET_B)])]


def raw(sources, rationale="발췌문에서 건설 연도가 확인됨", idx=0):
    return json.dumps({"results": [{"idx": idx, "sources": sources, "rationale": rationale}]}, ensure_ascii=False)


def src(sid, stance, quote="", same_scope=None):
    return {"sid": sid, "stance": stance, "same_scope": (stance != "neutral") if same_scope is None else same_scope, "quote": quote}


GOOD_QUOTE = "1889년에 파리 만국 박람회를 위해 건설되었다."


# ------------------------------------------------------------ find_quote


def test_find_quote_returns_actual_substring_of_snippet():
    assert find_quote(GOOD_QUOTE, SNIPPET_A) == GOOD_QUOTE


def test_find_quote_tolerates_whitespace_and_invisible_characters():
    assert find_quote("1889년에   파리 만국\n박람회를 위해 건설되었다.", SNIPPET_A) == GOOD_QUOTE
    assert find_quote("1889년에 파리\u200b 만국 박람회를 위해 건설되었다.", SNIPPET_A) == GOOD_QUOTE


def test_find_quote_tolerates_unicode_normalization_forms():
    decomposed = unicodedata.normalize("NFD", GOOD_QUOTE)
    assert decomposed != GOOD_QUOTE
    assert find_quote(decomposed, SNIPPET_A) == GOOD_QUOTE


def test_find_quote_rejects_missing_changed_short_and_long_quotes():
    assert find_quote("에펠탑은 1887년에 건설되었다고 한다.", SNIPPET_A) is None  # 없는 문장
    assert find_quote("1889년에 파리 박람회를 위해 건설되었다.", SNIPPET_A) is None  # 한 단어가 빠진 변형
    assert find_quote("1889년", SNIPPET_A) is None  # 너무 짧음
    assert find_quote("가" * 301, "가" * 400) is None  # 너무 김
    assert find_quote("", SNIPPET_A) is None


# ------------------------------------------------------------ derive_status


def v(stance):
    return SourceVerdict(0, stance, "q" if stance != "neutral" else "", False)


def test_derive_status():
    assert derive_status([v("neutral"), v("neutral")]) == ("insufficient", "low")
    assert derive_status([v("supports"), v("neutral")]) == ("supported", "medium")
    assert derive_status([v("supports"), v("supports")]) == ("supported", "high")
    assert derive_status([v("contradicts"), v("neutral")]) == ("contradicted", "medium")
    assert derive_status([v("contradicts"), v("contradicts")]) == ("contradicted", "high")
    assert derive_status([v("supports"), v("contradicts")]) == ("mixed", "low")
    assert derive_status([]) == ("insufficient", "low")


# ------------------------------------------------------------ parse_and_verify


def test_verified_support_gives_supported_with_real_quote():
    j = parse_and_verify(raw([src(0, "supports", GOOD_QUOTE), src(1, "neutral")]), ITEMS)[0]
    assert (j.status, j.confidence) == ("supported", "medium")
    assert j.source_verdicts[0] == SourceVerdict(0, "supports", GOOD_QUOTE, False)
    assert j.source_verdicts[1] == SourceVerdict(1, "neutral", "", False)


def test_fabricated_quote_is_downgraded_and_does_not_count():
    j = parse_and_verify(raw([src(0, "supports", "에펠탑은 1889년에 지어졌고 높이는 330m이다."), src(1, "neutral")]), ITEMS)[0]
    assert j.source_verdicts[0] == SourceVerdict(0, "neutral", "", True)  # 근거 취소, 취소됐다는 표시
    assert (j.status, j.confidence) == ("insufficient", "low")


def test_quote_must_come_from_that_sources_own_excerpt():
    # 1번 출처의 문장을 0번 출처의 근거로 대면 인정하지 않는다.
    j = parse_and_verify(raw([src(0, "supports", "귀스타브 에펠은 프랑스의 건축가이자 구조 공학자이다."), src(1, "neutral")]), ITEMS)[0]
    assert j.source_verdicts[0].downgraded is True and j.status == "insufficient"


def test_real_quote_about_a_different_scope_is_not_counted():
    # 실제 사례: 주장은 '2023년' 통계인데 발췌문은 '2022년' 통계. 인용문은 발췌문에 실제로 있지만 반박이 아니다.
    snippet = "2022년 기준, 대한민국의 합계출산율은 0.78명이다."
    items = [(0, "2023년 한국의 합계출산율은 0.72명이다.", [result("합계출산율", snippet)])]
    quote = "2022년 기준, 대한민국의 합계출산율은 0.78명이다."
    j = parse_and_verify(raw([src(0, "contradicts", quote, same_scope=False)]), items)[0]
    assert j.source_verdicts[0] == SourceVerdict(0, "neutral", "", True)
    assert (j.status, j.confidence) == ("insufficient", "low")
    # 같은 범위(같은 대상, 같은 시점)에서 값이 다르면 반박으로 인정한다.
    items = [(0, "2022년 한국의 합계출산율은 0.72명이다.", [result("합계출산율", snippet)])]
    j = parse_and_verify(raw([src(0, "contradicts", quote, same_scope=True)]), items)[0]
    assert j.status == "contradicted"


def test_same_scope_must_be_boolean():
    expect_error(raw([{"sid": 0, "stance": "neutral", "quote": ""}, src(1, "neutral")]))  # same_scope 없음
    expect_error(raw([{"sid": 0, "stance": "neutral", "same_scope": "yes", "quote": ""}, src(1, "neutral")]))


def test_two_verified_supports_give_high_and_mixed_gives_low():
    q2 = "에펠탑의 설계에 참여했다."
    j = parse_and_verify(raw([src(0, "supports", GOOD_QUOTE), src(1, "supports", q2)]), ITEMS)[0]
    assert (j.status, j.confidence) == ("supported", "high")
    j = parse_and_verify(raw([src(0, "supports", GOOD_QUOTE), src(1, "contradicts", q2)]), ITEMS)[0]
    assert (j.status, j.confidence) == ("mixed", "low")


def test_neutral_with_junk_quote_is_ignored():
    j = parse_and_verify(raw([src(0, "neutral", "아무 말"), src(1, "neutral", GOOD_QUOTE)]), ITEMS)[0]
    assert all(s.quote == "" and not s.downgraded for s in j.source_verdicts)


def test_rationale_with_definitive_words_is_dropped_and_long_is_truncated():
    j = parse_and_verify(raw([src(0, "neutral"), src(1, "neutral")], rationale="이 주장은 사실이다."), ITEMS)[0]
    assert j.rationale == ""
    j = parse_and_verify(raw([src(0, "neutral"), src(1, "neutral")], rationale="가" * 500), ITEMS)[0]
    assert len(j.rationale) == 200
    j = parse_and_verify(raw([src(0, "neutral"), src(1, "neutral")], rationale="발췌문에서 연도가 확인됨"), ITEMS)[0]
    assert j.rationale == "발췌문에서 연도가 확인됨"


def expect_error(text, items=ITEMS):
    try:
        parse_and_verify(text, items)
    except ValueError:
        return
    raise AssertionError(f"ValueError가 나야 한다: {text[:80]}")


def test_structure_errors_raise_value_error():
    ok = [src(0, "neutral"), src(1, "neutral")]
    expect_error("not json")
    expect_error("{}")
    expect_error('{"results": null}')
    expect_error('{"results": [1]}')
    expect_error(raw(ok, idx=5))  # 없는 idx → 누락
    expect_error(json.dumps({"results": [{"idx": 0, "sources": ok, "rationale": ""}] * 2}))  # idx 중복
    expect_error(raw([src(0, "neutral")]))  # sid 누락
    expect_error(raw([src(0, "neutral"), src(0, "neutral")]))  # sid 중복
    expect_error(raw([src(0, "neutral"), src(5, "neutral")]))  # 없는 sid
    expect_error(raw([src(0, "supports?"), src(1, "neutral")]))  # 허용되지 않는 stance
    expect_error(raw([{"sid": 0, "stance": "supports", "same_scope": True, "quote": None}, src(1, "neutral")]))  # quote가 문자열 아님
    expect_error(json.dumps({"results": [{"idx": 0, "sources": "x", "rationale": ""}]}))


# ------------------------------------------------------------ judge_claims (가짜 Claude)


class _Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Usage:
    def __init__(self, i=100, o=50):
        self.input_tokens, self.output_tokens = i, o


class _Response:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = _Usage()


class FakeClient:
    """요청 내용에서 응답을 계산한다. (스레드 실행 순서와 무관하게 결과가 정해진다)"""

    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self.lock = threading.Lock()
        self.messages = self

    def create(self, **kwargs):
        payload = json.loads(kwargs["messages"][0]["content"].split("\n\n", 1)[1])
        with self.lock:
            self.calls.append([p["idx"] for p in payload])
        return self.responder(payload, len(self.calls))


def support_first_source(payload, _call_no):
    """각 문장의 0번 출처 발췌문 전체(앞 40자)를 근거로 supports, 나머지는 neutral."""
    results = []
    for p in payload:
        quote = p["sources"][0]["excerpt"][:40]
        sources = [{"sid": 0, "stance": "supports", "same_scope": True, "quote": quote}]
        sources += [{"sid": s["sid"], "stance": "neutral", "same_scope": False, "quote": ""} for s in p["sources"][1:]]
        results.append({"idx": p["idx"], "sources": sources, "rationale": "발췌문에서 확인됨"})
    return _Response(json.dumps({"results": results}, ensure_ascii=False))


@contextmanager
def judge_settings(**overrides):
    saved = {k: getattr(settings, k) for k in overrides}
    for k, val in overrides.items():
        setattr(settings, k, val)
    try:
        yield
    finally:
        for k, val in saved.items():
            setattr(settings, k, val)


def many_items(n):
    long = "에펠탑은 프랑스 파리에 있는 격자형 철골 타워로 1889년에 건설되었다. 높이는 약 330미터이다."
    return [(i, f"주장 {i}", [result(f"문서{i}", long), result(f"다른문서{i}", SNIPPET_B)]) for i in range(n)]


def test_judge_claims_chunks_and_collects_everything():
    client = FakeClient(support_first_source)
    with judge_settings(judge_chunk_size=2, judge_concurrency=2):
        res = judge_claims(many_items(5), client=client)
    assert sorted(len(c) for c in client.calls) == [1, 2, 2]  # 2+2+1로 나뉘어 3번 호출
    assert sorted(res.judgments) == [0, 1, 2, 3, 4] and res.failed == {}
    assert all(j.status == "supported" for j in res.judgments.values())
    assert (res.usage.input_tokens, res.usage.output_tokens) == (300, 150)  # 3번 호출의 합


def test_judge_claims_empty_makes_no_call():
    client = FakeClient(support_first_source)
    res = judge_claims([], client=client)
    assert client.calls == [] and res.judgments == {} and res.failed == {}


def test_invalid_response_is_retried_once_then_succeeds():
    def responder(payload, call_no):
        if call_no == 1:
            return _Response('{"results": []}')  # idx 누락
        return support_first_source(payload, call_no)

    client = FakeClient(responder)
    with judge_settings(judge_chunk_size=8):
        res = judge_claims(many_items(2), client=client)
    assert len(client.calls) == 2 and sorted(res.judgments) == [0, 1] and res.failed == {}


def test_persistently_invalid_response_marks_only_that_chunk_failed():
    def responder(payload, call_no):
        if any(p["idx"] == 0 for p in payload):
            return _Response("not json")  # 0번이 든 묶음은 계속 깨진 응답
        return support_first_source(payload, call_no)

    client = FakeClient(responder)
    with judge_settings(judge_chunk_size=2, judge_concurrency=1):
        res = judge_claims(many_items(4), client=client)
    assert res.failed == {0: "judge_failed", 1: "judge_failed"}  # 한 묶음만 실패
    assert sorted(res.judgments) == [2, 3]  # 나머지는 살아남음


def test_api_errors_are_isolated_and_coded():
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def responder(payload, call_no):
        if any(p["idx"] == 0 for p in payload):
            raise anthropic.APIConnectionError(request=request)
        return support_first_source(payload, call_no)

    client = FakeClient(responder)
    with judge_settings(judge_chunk_size=2, judge_concurrency=2):
        res = judge_claims(many_items(4), client=client)
    assert res.failed == {0: "unavailable", 1: "unavailable"} and sorted(res.judgments) == [2, 3]


def test_refusal_and_truncation_mark_chunk_failed():
    for stop_reason in ("refusal", "max_tokens"):
        client = FakeClient(lambda payload, n, s=stop_reason: _Response("{}", stop_reason=s))
        res = judge_claims(many_items(1), client=client)
        assert res.failed == {0: "judge_failed"} and res.judgments == {}
