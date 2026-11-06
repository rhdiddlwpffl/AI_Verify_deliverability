"""여러 테스트가 함께 쓰는 가짜(fake) 객체.
분류, 검색, 비교, 호출 제한을 가짜로 바꿔 끼우면 비용 없이 응답 조립과 HTTP 동작을 확인할 수 있다."""

from contextlib import contextmanager
from types import SimpleNamespace

from app.services import pipeline, rate_limit
from app.services.claim_extractor import ClaimAnalysis, ClassificationResult, TokenUsage
from app.services.searcher import SearchResult, SearchUnavailableError
from app.services.verifier import JudgeResult, Judgment, SourceVerdict

TEXT = "😀 에펠탑은 1889년에 지어졌다. 이 문장은 검색이 실패한다. 정말 멋지다."
REQUEST = SimpleNamespace(client=SimpleNamespace(host="203.0.113.9"), headers={})


class AllowAllLimiter:
    """이 파일의 테스트는 응답 조립을 보는 것이므로, 호출 횟수 제한은 항상 통과시킨다.
    (제한 자체는 test_rate_limit.py에서 확인한다)"""

    def admit_analysis(self, ip):
        pass

    @contextmanager
    def analysis_slot(self):
        yield


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
    original = (pipeline.classify_sentences, pipeline.get_provider, pipeline.judge_claims, rate_limit.limiter)
    pipeline.classify_sentences = fake_classify
    pipeline.get_provider = lambda: FakeProvider()
    pipeline.judge_claims = judge
    rate_limit.limiter = AllowAllLimiter()
    try:
        yield
    finally:
        (pipeline.classify_sentences, pipeline.get_provider, pipeline.judge_claims, rate_limit.limiter) = original


def js_slice(text, start, end):
    return text.encode("utf-16-le")[start * 2 : end * 2].decode("utf-16-le")


# ------------------------------------------------------------ 가짜 Claude 클라이언트


class FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class FakeUsage:
    def __init__(self, input_tokens=100, output_tokens=50):
        self.input_tokens, self.output_tokens = input_tokens, output_tokens


class FakeResponse:
    def __init__(self, text, stop_reason="end_turn", input_tokens=100, output_tokens=50):
        self.content = [FakeBlock(text)]
        self.stop_reason = stop_reason
        self.usage = FakeUsage(input_tokens, output_tokens)


class FakeLLMClient:
    """messages.create(**kwargs)를 흉내 낸다. responder(kwargs, 호출 순번)가 응답을 만들거나 예외를 던진다.
    받은 요청은 self.calls에 남겨서 '무엇을 보냈는지'도 확인할 수 있다."""

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responder(kwargs, len(self.calls))
