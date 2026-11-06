from typing import Annotated

from fastapi import Header

from app.core.errors import AppError
from app.services.anon_token import hash_token, is_valid_token


def optional_token_hash(x_anon_token: Annotated[str | None, Header()] = None) -> str | None:
    """X-Anon-Token 헤더가 있으면 검증해서 해시를 돌려준다. 없으면 None. 형식이 이상하면 400."""
    if x_anon_token is None:
        return None
    if not is_valid_token(x_anon_token):
        raise AppError(400, "invalid_token", "기록 식별 정보의 형식이 올바르지 않습니다. 페이지를 새로고침해 주세요.")
    return hash_token(x_anon_token)


def required_token_hash(x_anon_token: Annotated[str | None, Header()] = None) -> str:
    """기록을 읽거나 지우는 요청에는 토큰이 반드시 있어야 한다."""
    token_hash = optional_token_hash(x_anon_token)
    if token_hash is None:
        raise AppError(401, "missing_token", "기록을 확인할 수 없습니다. 페이지를 새로고침해 주세요.")
    return token_hash
