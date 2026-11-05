from app.services.sentence_splitter import split_sentences


def texts(src: str) -> list[str]:
    return [s.text for s in split_sentences(src)]


def test_korean_basic_and_question_exclamation():
    assert texts("서울의 인구는 약 950만 명이다. 이는 가장 많다! 정말일까?") == [
        "서울의 인구는 약 950만 명이다.",
        "이는 가장 많다!",
        "정말일까?",
    ]


def test_decimals_and_urls_do_not_split():
    src = "파이는 약 3.14입니다. 자세한 내용은 https://example.com/a.b 를 보세요."
    assert texts(src) == [
        "파이는 약 3.14입니다.",
        "자세한 내용은 https://example.com/a.b 를 보세요.",
    ]


def test_english_abbreviations_do_not_split():
    assert texts("Dr. Smith wrote this, e.g. in 2020. It was good.") == [
        "Dr. Smith wrote this, e.g. in 2020.",
        "It was good.",
    ]


def test_list_markers_and_newlines():
    src = "요약:\n1. 첫째 항목입니다.\n2. 둘째 항목입니다.\n- 셋째"
    assert texts(src) == ["요약:", "첫째 항목입니다.", "둘째 항목입니다.", "셋째"]


def test_code_fence_and_separator_lines_skipped():
    src = "설명입니다.\n```\nx = 1. y = 2.\n```\n---\n끝입니다."
    assert texts(src) == ["설명입니다.", "끝입니다."]


def test_closing_brackets_stay_with_sentence():
    assert texts("(참고: 2020년 자료.) 다음 문장.") == ["(참고: 2020년 자료.)", "다음 문장."]


def test_ellipsis():
    assert texts("기다렸다... 그리고 떠났다.") == ["기다렸다...", "그리고 떠났다."]


def test_offsets_always_match_source():
    src = "  첫 문장입니다.  \r\n\r\n   두 번째 문장! 세 번째 문장?\n\n- 목록 문장.\n마지막 줄"
    result = split_sentences(src)
    assert result, "문장이 하나도 없으면 안 된다"
    for i, s in enumerate(result):
        assert s.idx == i
        assert src[s.start : s.end] == s.text
        assert s.text == s.text.strip()


def test_empty_and_whitespace_only():
    assert split_sentences("") == []
    assert split_sentences("  \n\t \n") == []
