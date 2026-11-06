from app.api.deps import optional_token_hash, required_token_hash
from app.core.errors import AppError
from app.services.anon_token import hash_token, is_valid_token

GOOD = "a1b2c3d4" * 8  # 64자 16진수


def test_hash_is_deterministic_hex_and_not_the_token():
    h = hash_token(GOOD)
    assert h == hash_token(GOOD) and len(h) == 64 and h != GOOD
    assert hash_token(GOOD) != hash_token(GOOD[:-1] + "0")


def test_token_format_validation():
    assert is_valid_token(GOOD) and is_valid_token("A" * 32) and is_valid_token("a-b_c" * 8)
    for bad in ("", "short", "a" * 31, "a" * 129, "a" * 31 + " ", "a" * 31 + "한", "a" * 31 + "'", "a" * 31 + "\n"):
        assert not is_valid_token(bad), bad


def test_optional_dependency():
    assert optional_token_hash(None) is None
    assert optional_token_hash(GOOD) == hash_token(GOOD)
    try:
        optional_token_hash("bad token!")
    except AppError as exc:
        assert (exc.status_code, exc.code) == (400, "invalid_token")
        return
    raise AssertionError("AppError가 나야 한다")


def test_required_dependency():
    assert required_token_hash(GOOD) == hash_token(GOOD)
    try:
        required_token_hash(None)
    except AppError as exc:
        assert (exc.status_code, exc.code) == (401, "missing_token")
        return
    raise AssertionError("AppError가 나야 한다")
