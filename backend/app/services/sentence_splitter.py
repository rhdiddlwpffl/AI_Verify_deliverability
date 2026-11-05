"""AI 답변을 문장 단위로 나누고, 원문에서의 정확한 위치(start/end)를 함께 돌려준다.

핵심 약속: 모든 문장에서 `text == 원문[start:end]` 가 성립한다.
화면에서 문장을 하이라이트할 때 이 위치를 그대로 쓰기 때문이다.
(LLM에게 문장 분리를 맡기지 않는 이유: 글자 위치를 틀리거나 문장을 바꿔 쓸 수 있다.)

알려진 한계: 따옴표 안의 마침표("맞다." 라고 했다)에서는 문장이 나뉠 수 있다.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sentence:
    idx: int  # 0부터 시작하는 순번
    text: str
    start: int  # 원문에서의 시작 위치 (포함)
    end: int  # 원문에서의 끝 위치 (미포함)


# 문장 끝 기호(연속 가능) + 뒤따르는 닫는 따옴표/괄호. 그 뒤에 공백이나 줄 끝이 와야 경계로 본다.
# → "3.14", "example.com" 처럼 점 뒤에 바로 글자가 오면 경계가 아니다.
_TERMINATOR = re.compile(r"[.!?。！？…]+[\"'”’)\]」』]*(?=\s|$)")
_CLOSERS = "\"'”’)]」』"

_LINE = re.compile(r"[^\r\n]+")
_LIST_MARKER = re.compile(r"^[ \t]*(?:[-*+•]|\d{1,3}[.)])[ \t]+")
_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")

# 뒤에 마침표가 붙어도 문장이 끝나지 않는 영어 약어 (소문자, 마지막 점 제외)
# 'etc', 'no' 처럼 문장 끝에도 자주 쓰이는 말은 일부러 뺐다.
_ABBREVIATIONS = {
    "e.g", "i.e", "vs", "dr", "mr", "mrs", "ms", "prof",
    "inc", "ltd", "u.s", "u.k", "a.m", "p.m", "fig", "approx",
}
_WORD_BEFORE = re.compile(r"([A-Za-z][A-Za-z.]*)$")


def _is_false_boundary(segment: str, match: re.Match[str]) -> bool:
    """마침표가 영어 약어의 일부라서 문장 끝이 아닌 경우."""
    if match.group().rstrip(_CLOSERS) != ".":
        return False
    word = _WORD_BEFORE.search(segment[: match.start()])
    return bool(word) and word.group(1).lower() in _ABBREVIATIONS


def split_sentences(text: str) -> list[Sentence]:
    sentences: list[Sentence] = []
    in_fence = False

    def emit(chunk_start: int, chunk: str) -> None:
        stripped = chunk.strip()
        # 글자나 숫자가 하나도 없으면(예: '---', '|---|') 문장이 아니다.
        if not stripped or not any(ch.isalnum() for ch in stripped):
            return
        start = chunk_start + (len(chunk) - len(chunk.lstrip()))
        end = start + len(stripped)
        sentences.append(Sentence(idx=len(sentences), text=text[start:end], start=start, end=end))

    for line in _LINE.finditer(text):
        raw = line.group()
        if _FENCE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        marker = _LIST_MARKER.match(raw) or _HEADING.match(raw)
        skip = marker.end() if marker else 0
        segment = raw[skip:]
        base = line.start() + skip

        cursor = 0
        for term in _TERMINATOR.finditer(segment):
            if _is_false_boundary(segment, term):
                continue
            emit(base + cursor, segment[cursor : term.end()])
            cursor = term.end()
        emit(base + cursor, segment[cursor:])

    return sentences
