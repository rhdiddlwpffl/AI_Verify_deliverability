"""익명 사용자 토큰 처리.

브라우저가 만든 무작위 토큰을 헤더(X-Anon-Token)로 받아서, 서버에는 SHA-256 해시만 저장한다.
토큰 원본을 저장하지 않으므로 DB가 유출돼도 그 토큰으로 남의 기록을 열 수 없다.
(토큰이 256비트 무작위 값이라 솔트 없이 해시해도 추측하기 어렵다)
"""

import hashlib
import re

# 브라우저가 만드는 토큰: 64자 16진수(256비트). 길이와 문자만 느슨하게 제한해 이상한 입력을 막는다.
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")


def is_valid_token(token: str) -> bool:
    return bool(_TOKEN_PATTERN.fullmatch(token))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
