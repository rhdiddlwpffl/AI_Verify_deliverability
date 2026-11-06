"""POST /analyses 라우트 함수를 직접 호출해서 응답 조립을 확인한다.
분류, 검색, 비교는 모두 가짜로 바꿔 끼우므로 비용이 들지 않는다. (가짜는 tests/fakes.py)"""

from app.api.routes.analyses import create_analysis
from app.schemas.analysis import AnalyzeRequest
from tests.fakes import REQUEST, TEXT, fake_judge_fails, js_slice, patched


def test_response_combines_classification_search_and_verification():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT), REQUEST, None)

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
        resp = create_analysis(AnalyzeRequest(text=TEXT), REQUEST, None)
    found = resp.claims[0]
    assert found.verification_status == "unverified" and found.verification_error == "judge_failed"
    assert found.verification_confidence is None and found.verification_rationale is None
    # 비교에 실패해도 찾은 문서는 그대로 보여 준다. 이때 출처별 stance는 비어 있다.
    assert len(found.sources) == 2 and all(s.stance is None and s.quote == "" for s in found.sources)
    assert resp.claims[1].verification_status == "search_failed"  # 다른 문장은 영향 없음


def test_offsets_are_javascript_based_even_with_emoji_before_the_text():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT), REQUEST, None)
    for c in resp.claims:
        assert js_slice(TEXT, c.start, c.end) == c.text


# ------------------------------------------------------------ 저장 경로 (DB 없이 가짜로 확인)

from app.api.routes import analyses as route_module  # noqa: E402


def test_default_is_not_saved_and_never_touches_the_db():
    called = []
    original = route_module._try_save
    route_module._try_save = lambda *a, **k: called.append(1) or ("saved", "x")
    try:
        with patched():
            resp = create_analysis(AnalyzeRequest(text=TEXT), REQUEST, "a" * 64)  # 토큰이 있어도 save를 켜지 않으면 저장 안 함
    finally:
        route_module._try_save = original
    assert called == [] and resp.save_status == "not_requested" and resp.analysis_id is None


def test_save_requested_without_token_reports_no_token():
    with patched():
        resp = create_analysis(AnalyzeRequest(text=TEXT, save=True), REQUEST, None)
    assert resp.save_status == "no_token" and resp.analysis_id is None
    assert resp.check_worthy_count == 2  # 분석 결과 자체는 정상


def test_save_failure_does_not_lose_the_analysis_result():
    from sqlalchemy.exc import OperationalError

    def broken_engine():
        raise OperationalError("select 1", {}, Exception("connection refused: " + "postgresql" + "://user:fake@host"))

    original = route_module.get_engine
    route_module.get_engine = broken_engine
    try:
        with patched():
            resp = create_analysis(AnalyzeRequest(text=TEXT, save=True), REQUEST, "a" * 64)
    finally:
        route_module.get_engine = original
    assert resp.save_status == "failed" and resp.analysis_id is None
    assert resp.check_worthy_count == 2 and resp.claims[0].verification_status == "supported"  # 결과는 그대로
    assert "secret" not in resp.model_dump_json()  # 예외 내용(접속 정보)이 응답에 섞이지 않는다


def test_saved_response_carries_the_analysis_id():
    original = route_module._try_save
    route_module._try_save = lambda token_hash, text, data: ("saved", "11111111-1111-1111-1111-111111111111")
    try:
        with patched():
            resp = create_analysis(AnalyzeRequest(text=TEXT, save=True), REQUEST, "a" * 64)
    finally:
        route_module._try_save = original
    assert resp.save_status == "saved" and resp.analysis_id == "11111111-1111-1111-1111-111111111111"
