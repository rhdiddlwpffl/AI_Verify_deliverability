"""확인 필요 문장마다 검색해서 근거 후보(문서)를 모은다.

- 같은 검색어는 한 번만 검색한다. (위키미디어에 불필요한 요청을 보내지 않기 위해)
- 동시에 보내는 요청 수를 제한한다. (위키미디어는 순차/소량 요청을 권장)
- 일부가 실패해도 나머지는 살린다. 실패는 '찾지 못함'과 구분해서 기록한다.
- 이 모듈은 검색된 문서가 주장을 '뒷받침하는지'는 판단하지 않는다. (8단계)
"""

import logging
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field

from app.models.enums import SearchStatus
from app.services.claim_extractor import ClaimAnalysis
from app.services.searcher import (
    SearchError,
    SearchProvider,
    SearchRateLimitedError,
    SearchResult,
    SearchUnavailableError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Evidence:
    status: str  # SearchStatus 값
    error: str | None = None  # status가 failed일 때: rate_limited | unavailable | timeout | error
    results: list[SearchResult] = field(default_factory=list)


def _search_one(provider: SearchProvider, query: str) -> Evidence:
    try:
        results = provider.search(query)
    except SearchRateLimitedError:
        return Evidence(SearchStatus.FAILED.value, "rate_limited")
    except SearchUnavailableError:
        return Evidence(SearchStatus.FAILED.value, "unavailable")
    except SearchError:
        return Evidence(SearchStatus.FAILED.value, "error")
    except Exception as exc:  # noqa: BLE001  한 문장의 예상 못 한 오류가 전체를 망치지 않게 한다.
        logger.error("검색 중 예상하지 못한 오류: %s", type(exc).__name__)
        return Evidence(SearchStatus.FAILED.value, "error")
    status = SearchStatus.FOUND if results else SearchStatus.NONE
    return Evidence(status.value, None, results)


def gather_evidence(
    claims: list[ClaimAnalysis],
    provider: SearchProvider,
    *,
    max_claims: int,
    concurrency: int,
    timeout: float,
) -> dict[int, Evidence]:
    """문장 번호(idx) → 검색 결과. 확인 대상이 아닌 문장은 NOT_SEARCHED."""
    evidence = {c.sentence.idx: Evidence(SearchStatus.NOT_SEARCHED.value) for c in claims}

    checkable = [c for c in claims if c.check_worthy]
    targets, skipped = checkable[:max_claims], checkable[max_claims:]
    for c in skipped:
        evidence[c.sentence.idx] = Evidence(SearchStatus.SKIPPED.value)
    if not targets:
        return evidence

    queries = list(dict.fromkeys(c.search_query for c in targets))  # 순서를 유지한 중복 제거
    executor = ThreadPoolExecutor(max_workers=concurrency)
    futures = {q: executor.submit(_search_one, provider, q) for q in queries}
    _, not_done = wait(futures.values(), timeout=timeout)
    # 아직 시작하지 않은 검색은 취소한다. 이미 실행 중인 검색은 각자의 제한 시간 안에 끝난다.
    executor.shutdown(wait=False, cancel_futures=True)

    by_query = {
        q: Evidence(SearchStatus.FAILED.value, "timeout") if f in not_done or f.cancelled() else f.result()
        for q, f in futures.items()
    }
    for c in targets:
        evidence[c.sentence.idx] = by_query[c.search_query]

    counts = {s.value: 0 for s in SearchStatus}
    for e in by_query.values():
        counts[e.status] += 1
    logger.info(
        "검색 완료: 검색어 %d개 (찾음 %d, 없음 %d, 실패 %d), 제한으로 건너뜀 %d문장",
        len(queries),
        counts[SearchStatus.FOUND.value],
        counts[SearchStatus.NONE.value],
        counts[SearchStatus.FAILED.value],
        len(skipped),
    )
    return evidence
