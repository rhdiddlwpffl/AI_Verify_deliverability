"""POST /analyses 라우트 함수를 직접 호출해서 응답 조립을 확인한다.
분류(Claude)와 검색(위키백과)은 가짜로 바꿔 끼우므로 비용이 들지 않는다."""

from contextlib import contextmanager

from app.api.routes.analyses import create_analysis
from app.schemas.analysis import AnalyzeRequest
from app.services import pipeline
from app.services.claim_extractor import ClaimAnalysis, ClassificationResult, TokenUsage
from app.services.searcher import SearchResult, SearchUnavailableError

TEXT = "😀 에펠탑은 1889년에 지어졌다. 이 문장은 검색이 실패한다. 정말 멋지다."


def fake_classify(sentences):
    plan = [
        ("numeric", True, ["contains_number"], "에펠탑"),
        ("factual", True, ["absolute_expression"], "실패검색어"),
        ("opinion", False, ["absolute_expression"], ""),  # 확인 대상이 아닌데 신호가 붙은 경우
    ]
    claims = [ClaimAnalysis(s, t, w, f, "이유", q) for s, (t, w, f, q) in zip(sentences, plan, strict=True)]
    return ClassificationResult(claims=claims, model="fake-model", usage=TokenUsage(1, 1))


class FakeProvider:
    def search(self, query):
        if query == "실패검색어":
            raise SearchUnavailableError("down")
        return [SearchResult("에펠탑", "https://ko.wikipedia.org/wiki/에펠탑", "에펠탑은 1889년에 …", "wikipedia-ko")]


@contextmanager
def patched():
    original = (pipeline.classify_sentences, pipeline.get_provider)
    pipeline.classify_sentences = fake_classify
    pipeline.get_provider = lambda: FakeProvider()
    try:
        yield
    finally:
        pipeline.classify_sentences, pipeline.get_provider = original


def js_slice(text, start, end):
    return text.encode("utf-16-le")[start * 2 : end * 2].decode("utf-16-le")


def test_response_combines_classification_and_search_with_partial_failure():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT))

    assert (resp.sentence_count, resp.check_worthy_count, resp.model) == (3, 2, "fake-model")
    found, failed, opinion = resp.claims

    assert found.search_status == "found" and found.search_error is None
    assert found.search_query == "에펠탑" and [s.source for s in found.sources] == ["wikipedia-ko"]

    # 검색이 실패해도 분석 전체는 성공하고, 그 문장만 failed로 표시된다. ('찾지 못함(none)'과 다르다)
    assert failed.search_status == "failed" and failed.search_error == "unavailable" and failed.sources == []

    assert opinion.search_status == "not_searched" and opinion.search_query == ""
    assert opinion.flags == []  # 확인 대상이 아닌 문장의 신호는 숨긴다
    assert found.flags == ["contains_number"]


def test_offsets_are_javascript_based_even_with_emoji_before_the_text():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT))
    for c in resp.claims:
        assert js_slice(TEXT, c.start, c.end) == c.text
