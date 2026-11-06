"""모든 테스트에 적용되는 공통 설정과 안전장치.

- db 마커가 붙은 테스트는 DATABASE_URL이 없으면 '건너뜀'으로 표시한다. (조용히 통과한 것처럼 보이지 않게)
- 테스트가 실수로 실제 Claude나 위키백과를 호출하지 못하게 막는다. (비용, 속도 한도, 재현성 때문에)
  필요한 곳은 가짜(fake)를 직접 끼워 넣는다.
"""

import logging

import pytest

from app.core.config import settings
from app.services import claim_extractor

_REAL_GET_CLIENT = claim_extractor.get_client  # 자동 차단 장치가 가리기 전의 진짜 함수


def pytest_collection_modifyitems(config, items):
    if settings.database_url:
        return
    skip_db = pytest.mark.skip(reason="DATABASE_URL이 없어 DB 통합 테스트를 건너뜁니다.")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)


@pytest.fixture(autouse=True)
def forbid_real_external_calls(monkeypatch):
    """실제 Claude/위키백과 호출을 막는다. 걸리면 테스트가 실패해서 바로 알 수 있다."""

    def blocked(*args, **kwargs):
        raise AssertionError("테스트에서 외부 서비스(Claude, 위키백과)를 실제로 호출하면 안 됩니다. 가짜를 끼워 넣으세요.")

    import urllib.request

    from app.services import claim_extractor, verifier

    monkeypatch.setattr(urllib.request, "urlopen", blocked)  # 위키백과 (검색 모듈의 기본 HTTP 호출)
    monkeypatch.setattr(claim_extractor, "get_client", blocked)  # Claude 기본 클라이언트
    monkeypatch.setattr(verifier, "get_client", blocked)


@pytest.fixture(autouse=True)
def quiet_logs():
    """오류 경로 테스트가 일부러 만드는 경고 로그가 출력을 어지럽히지 않게 한다."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def real_get_client():
    """get_client 자체를 확인하는 테스트용. (lru_cache를 비우고, 끝나면 다시 비운다)"""
    _REAL_GET_CLIENT.cache_clear()
    yield _REAL_GET_CLIENT
    _REAL_GET_CLIENT.cache_clear()
