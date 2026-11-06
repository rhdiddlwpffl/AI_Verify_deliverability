import threading
import time

from app.services.claim_extractor import ClaimAnalysis
from app.services.evidence import gather_evidence
from app.services.searcher import (
    SearchBadResponseError,
    SearchRateLimitedError,
    SearchResult,
    SearchUnavailableError,
)
from app.services.sentence_splitter import Sentence


def claim(idx, query, check_worthy=True):
    s = Sentence(idx=idx, text=f"문장 {idx}", start=idx * 10, end=idx * 10 + 5)
    return ClaimAnalysis(s, "factual", check_worthy, [], "r", query if check_worthy else "")


def result(title):
    return SearchResult(title=title, url=f"https://ko.wikipedia.org/wiki/{title}", snippet=f"{title} 소개", source="wikipedia-ko")


class FakeProvider:
    """query → 결과 목록 또는 던질 예외. 호출 기록을 남긴다."""

    def __init__(self, behaviors, delay=0.0):
        self.behaviors = behaviors
        self.delay = delay
        self.calls = []
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def search(self, query):
        with self.lock:
            self.calls.append(query)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            behavior = self.behaviors[query]
            if isinstance(behavior, Exception):
                raise behavior
            return behavior
        finally:
            with self.lock:
                self.active -= 1


def run(claims, provider, max_claims=20, concurrency=3, timeout=5.0):
    return gather_evidence(claims, provider, max_claims=max_claims, concurrency=concurrency, timeout=timeout)


def test_statuses_found_none_and_not_searched():
    provider = FakeProvider({"에펠탑": [result("에펠탑")], "없는말": []})
    ev = run([claim(0, "에펠탑"), claim(1, "없는말"), claim(2, "", check_worthy=False)], provider)
    assert ev[0].status == "found" and [r.title for r in ev[0].results] == ["에펠탑"]
    assert ev[1].status == "none" and ev[1].results == []
    assert ev[2].status == "not_searched"


def test_same_query_is_searched_once_and_shared():
    provider = FakeProvider({"에펠탑": [result("에펠탑")]})
    ev = run([claim(0, "에펠탑"), claim(1, "에펠탑"), claim(2, "에펠탑")], provider)
    assert provider.calls == ["에펠탑"]
    assert all(ev[i].status == "found" for i in range(3))


def test_partial_failures_are_isolated_and_classified():
    provider = FakeProvider(
        {
            "ok": [result("ok")],
            "limited": SearchRateLimitedError("x"),
            "down": SearchUnavailableError("x"),
            "bad": SearchBadResponseError("x"),
            "boom": RuntimeError("예상 못 한 오류"),
        }
    )
    ev = run([claim(i, q) for i, q in enumerate(["ok", "limited", "down", "bad", "boom"])], provider)
    assert ev[0].status == "found"
    assert (ev[1].status, ev[1].error) == ("failed", "rate_limited")
    assert (ev[2].status, ev[2].error) == ("failed", "unavailable")
    assert (ev[3].status, ev[3].error) == ("failed", "error")
    assert (ev[4].status, ev[4].error) == ("failed", "error")


def test_claims_over_the_limit_are_skipped_not_dropped():
    provider = FakeProvider({f"q{i}": [result(f"q{i}")] for i in range(5)})
    ev = run([claim(i, f"q{i}") for i in range(5)], provider, max_claims=3)
    assert [ev[i].status for i in range(5)] == ["found", "found", "found", "skipped", "skipped"]
    assert sorted(provider.calls) == ["q0", "q1", "q2"]  # 건너뛴 문장은 검색하지 않는다


def test_limit_keeps_claims_with_the_most_reasons_to_check_not_just_the_first_ones():
    # 앞에서부터 자르면 뒤쪽의 위험한 문장이 항상 빠진다. 신호가 많은 문장과 수치 주장을 먼저 고른다.
    def flagged(idx, flags, claim_type="factual"):
        c = claim(idx, f"q{idx}")
        return ClaimAnalysis(c.sentence, claim_type, True, flags, "r", f"q{idx}")

    claims = [
        flagged(0, []),  # 우선순위 0
        flagged(1, ["a"]),  # 1
        flagged(2, []),  # 0
        flagged(3, ["a", "b", "c"]),  # 3
        flagged(4, [], "numeric"),  # 1 (수치 주장 가산)
        flagged(5, ["a", "b"]),  # 2
    ]
    provider = FakeProvider({f"q{i}": [result(f"q{i}")] for i in range(6)})
    ev = run(claims, provider, max_claims=3)
    searched = sorted(i for i, e in ev.items() if e.status == "found")
    # 3번(3점), 5번(2점)이 먼저 뽑히고, 1점짜리(1번, 4번) 중에서는 앞 문장인 1번이 뽑힌다. (동점이면 앞 문장 우선)
    assert searched == [1, 3, 5]
    assert [i for i, e in ev.items() if e.status == "skipped"] == [0, 2, 4]  # 건너뛴 문장도 표시된다
    assert sorted(provider.calls) == ["q1", "q3", "q5"]


def test_non_checkworthy_claims_do_not_count_toward_the_limit():
    provider = FakeProvider({"a": [result("a")], "b": [result("b")]})
    claims = [claim(0, "", False), claim(1, "a"), claim(2, "", False), claim(3, "b")]
    ev = run(claims, provider, max_claims=2)
    assert ev[1].status == "found" and ev[3].status == "found"


def test_no_claims_means_no_search():
    provider = FakeProvider({})
    ev = run([claim(0, "", False)], provider)
    assert provider.calls == [] and ev[0].status == "not_searched"
    assert run([], provider) == {}


def test_concurrency_is_limited():
    provider = FakeProvider({f"q{i}": [result(f"q{i}")] for i in range(8)}, delay=0.05)
    run([claim(i, f"q{i}") for i in range(8)], provider, concurrency=2)
    assert provider.max_active <= 2


def test_phase_timeout_marks_unfinished_as_timeout_and_keeps_finished():
    provider = FakeProvider({"fast": [result("fast")], "slow": [result("slow")], "later": [result("later")]})
    original = provider.search

    def search(query):
        if query == "fast":
            return original(query)
        time.sleep(0.6)
        return original(query)

    provider.search = search
    started = time.time()
    ev = run([claim(0, "fast"), claim(1, "slow"), claim(2, "later")], provider, concurrency=1, timeout=0.2)
    assert time.time() - started < 0.5  # 느린 검색이 끝나기를 기다리지 않는다
    assert ev[0].status == "found"
    assert (ev[1].status, ev[1].error) == ("failed", "timeout")
    assert (ev[2].status, ev[2].error) == ("failed", "timeout")
