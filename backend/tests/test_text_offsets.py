from app.services.sentence_splitter import split_sentences
from app.services.text_offsets import utf16_offset_table


def js_slice(text: str, start: int, end: int) -> str:
    """JavaScript의 text.slice(start, end)를 흉내 낸다. (UTF-16 코드 단위 기준)"""
    units = text.encode("utf-16-le")
    return units[start * 2 : end * 2].decode("utf-16-le")


def test_bmp_only_text_is_unchanged():
    text = "한국어 문장입니다. 두 번째입니다."
    assert utf16_offset_table(text) == list(range(len(text) + 1))


def test_emoji_takes_two_units():
    table = utf16_offset_table("a😀b")
    assert table == [0, 1, 3, 4]


def test_sentence_offsets_match_javascript_slice_with_emoji():
    text = "좋은 아침입니다 😀😀. 에펠탑은 1889년에 지어졌습니다. 🗼 정말 높습니다!"
    table = utf16_offset_table(text)
    sentences = split_sentences(text)
    assert len(sentences) == 3
    for s in sentences:
        assert js_slice(text, table[s.start], table[s.end]) == s.text
