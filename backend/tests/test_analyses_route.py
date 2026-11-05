"""POST /analyses 라우트 함수를 직접 호출해서 응답 조립을 확인한다.
분류, 검색, 비교는 모두 가짜로 바꿔 끼우므로 비용이 들지 않는다."""

from contextlib import contextmanager

from app.api.routes.analyses import create_analysis
from app.schemas.analysis import AnalyzeRequest
from app.services import pipeline
from app.services.claim_extractor import ClaimAnalysis, ClassificationResult, TokenUsage
from app.services.searcher import SearchResult, SearchUnavailableError
from app.services.verifier import Judgment, JudgeResult, SourceVerdict

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
        return [
            SearchResult("에펠탑", "https://ko.wikipedia.org/wiki/에펠탑", "에펠탑은 1889년에 건설되었다.", "wikipedia-ko"),
            SearchResult("파리", "https://ko.wikipedia.org/wiki/파리", "파리는 프랑스의 수도이다.", "wikipedia-ko"),
        ]


def fake_judge_ok(items):
    res = JudgeResult(model="fake-judge")
    for idx, _claim, _results in items:
        verdicts = [SourceVerdict(0, "supports", "에펠탑은 1889년에 건설되었다.", False), SourceVerdict(1, "neutral", "", True)]
        res.judgments[idx] = Judgment(idx, verdicts, "supported", "medium", "발췌문에서 건설 연도가 확인됨")
    return res


def fake_judge_fails(items):
    return JudgeResult(failed={idx: "judge_failed" for idx, _, _ in items}, model="fake-judge")


@contextmanager
def patched(judge=fake_judge_ok):
    original = (pipeline.classify_sentences, pipeline.get_provider, pipeline.judge_claims)
    pipeline.classify_sentences = fake_classify
    pipeline.get_provider = lambda: FakeProvider()
    pipeline.judge_claims = judge
    try:
        yield
    finally:
        pipeline.classify_sentences, pipeline.get_provider, pipeline.judge_claims = original


def js_slice(text, start, end):
    return text.encode("utf-16-le")[start * 2 : end * 2].decode("utf-16-le")


def test_response_combines_classification_search_and_verification():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT))

    assert (resp.sentence_count, resp.check_worthy_count, resp.model) == (3, 2, "fake-model")
    found, failed, opinion = resp.claims

    assert found.search_status == "found" and found.search_query == "에펠탑" and len(found.sources) == 2
    assert found.verification_status == "supported" and found.verification_confidence == "medium"
    assert found.verification_rationale == "발췌문에서 건설 연도가 확인됨" and found.verification_error is None
    # 출처별 비교 결과: 인용문이 확인된 근거와, 인용을 확인하지 못해 제외된 근거
    assert (found.sources[0].stance, found.sources[0].quote, found.sources[0].downgraded) == (
        "supports",
        "에펠탑은 1889년에 건설되었다.",
        False,
    )
    assert (found.sources[1].stance, found.sources[1].quote, found.sources[1].downgraded) == ("neutral", "", True)

    # 검색이 실패해도 분석 전체는 성공하고, 그 문장만 search_failed. ('찾지 못함'과 다르다)
    assert failed.search_status == "failed" and failed.search_error == "unavailable" and failed.sources == []
    assert failed.verification_status == "search_failed" and failed.verification_error == "unavailable"

    assert opinion.search_status == "not_searched" and opinion.verification_status == "not_checkable"
    assert opinion.flags == [] and found.flags == ["contains_number"]


def test_judge_failure_marks_only_unverified_and_keeps_sources():
    with patched(judge=fake_judge_fails):
        resp = create_analysis(AnalyzeRequest(text=TEXT))
    found = resp.claims[0]
    assert found.verification_status == "unverified" and found.verification_error == "judge_failed"
    assert found.verification_confidence is None and found.verification_rationale is None
    # 비교에 실패해도 찾은 문서는 그대로 보여 준다. 이때 출처별 stance는 비어 있다.
    assert len(found.sources) == 2 and all(s.stance is None and s.quote == "" for s in found.sources)
    assert resp.claims[1].verification_status == "search_failed"  # 다른 문장은 영향 없음


def test_offsets_are_javascript_based_even_with_emoji_before_the_text():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT))
    for c in resp.claims:
        assert js_slice(TEXT, c.start, c.end) == c.text
