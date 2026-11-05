def utf16_offset_table(text: str) -> list[int]:
    """파이썬 문자열 위치(글자 수) → JavaScript 문자열 위치(UTF-16 코드 단위) 변환표.

    table[i] = text[:i] 를 JavaScript에서 셌을 때의 길이.
    이모지 같은 큰 문자(U+FFFF 초과)는 JavaScript에서 2칸을 차지해서, 변환하지 않으면
    화면의 하이라이트가 뒤로 갈수록 밀린다.
    """
    table = [0] * (len(text) + 1)
    for i, ch in enumerate(text):
        table[i + 1] = table[i] + (2 if ord(ch) > 0xFFFF else 1)
    return table
