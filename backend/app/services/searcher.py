"""검색 근거 가져오기. 지금은 위키백과 API만 쓴다.

- 키/카드가 필요 없는 공식 API다. 대신 '설명이 담긴 User-Agent'가 필수다.
- 검색어는 사용자가 입력한 글에서 나오므로 로그에 남기지 않는다. (로그에는 오류 종류만)
- 제공자를 바꾸거나 추가할 수 있도록 SearchProvider 인터페이스 뒤에 둔다.
- 실패는 종류별 예외로 구분한다. (화면에서 '검색 실패'와 '근거 부족'을 다르게 보여 주기 위해)

HTTP 클라이언트로 표준 라이브러리 urllib를 쓰는 이유:
  같은 URL과 헤더로 보냈을 때 httpx2는 위키미디어에서 403("로봇 정책")을 받았고
  urllib/http.client는 200을 받았다. (2026-11 시험. 정확한 원인은 확인하지 못함)
  나중에 다른 HTTP 라이브러리로 바꾼다면 실제 위키백과로 먼저 시험할 것.
"""

import http.client
import json
import logging
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol
from urllib.parse import quote, urlencode

from app.core.config import settings

logger = logging.getLogger(__name__)

_HANGUL = re.compile(r"[ㄱ-ㆎ가-힣]")
# 폭 없는 공백(U+200B), 단어 결합자(U+2060), BOM(U+FEFF). 한글/영문 본문에서는 의미가 없다.
_INVISIBLE = re.compile("[\u200b\u2060\ufeff]")
_MAX_QUERY_CHARS = 200
_MAX_ATTEMPTS = 2  # 첫 시도 + 1회 재시도
_MAX_RETRY_WAIT_SECONDS = 5.0
_TIMEOUT_SECONDS = 8.0
_MAX_BODY_BYTES = 1_000_000


class SearchError(Exception):
    """검색에 실패했다."""


class SearchRateLimitedError(SearchError):
    """요청 한도를 넘었다. (HTTP 429 또는 ratelimited 응답)"""


class SearchUnavailableError(SearchError):
    """검색 서버에 연결하지 못했거나 시간이 초과되었거나 서버 오류(5xx)가 났다."""


class SearchBadResponseError(SearchError):
    """응답을 해석할 수 없거나, 재시도해도 소용없는 거절(예: 403 차단)이다."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str  # 문서 도입부의 순수 텍스트 (HTML 태그 없음)
    source: str  # 어느 검색 제공자인지. 예: "wikipedia-ko"


class SearchProvider(Protocol):
    def search(self, query: str) -> list[SearchResult]: ...


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]  # 키는 소문자
    body: bytes


# (url, params, headers, timeout) -> HttpResponse. 연결 실패/시간 초과는 OSError 계열 예외로 던진다.
Fetch = Callable[[str, dict[str, Any], dict[str, str], float], HttpResponse]


def _urllib_fetch(url: str, params: dict[str, Any], headers: dict[str, str], timeout: float) -> HttpResponse:
    request = urllib.request.Request(f"{url}?{urlencode(params)}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResponse(response.status, _lower_keys(response.headers), response.read(_MAX_BODY_BYTES))
    except urllib.error.HTTPError as exc:  # 4xx/5xx도 상태 코드와 본문으로 돌려준다
        return HttpResponse(exc.code, _lower_keys(exc.headers), exc.read(_MAX_BODY_BYTES))


def _lower_keys(headers: Any) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}


def detect_language(query: str) -> str:
    """검색어에 한글이 있으면 한국어 위키백과, 아니면 영어 위키백과를 쓴다."""
    return "ko" if _HANGUL.search(query) else "en"


def _clean_query(query: str) -> str:
    return " ".join(query.split())[:_MAX_QUERY_CHARS]


def _clean_text(text: str) -> str:
    # 눈에 보이지 않는 글자(폭 없는 공백 등)와 공백/줄바꿈을 정리한다.
    # 이후 '인용문이 발췌문에 실제로 있는지' 글자 단위로 비교할 때 오탐을 막기 위해서다.
    # NFC로 통일하는 이유: 같은 한글이 '완성형'과 '자모 분리형' 두 가지 코드로 저장될 수 있어서,
    # 통일하지 않으면 눈에는 같은 문장이 글자 비교에서 다르다고 나온다.
    return " ".join(unicodedata.normalize("NFC", _INVISIBLE.sub("", text)).split())


def _page_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='()_,!*~')}"


class WikipediaProvider:
    def __init__(
        self,
        *,
        fetch: Fetch = _urllib_fetch,
        user_agent: str | None = None,
        results: int | None = None,
        extract_chars: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._fetch = fetch
        self._user_agent = user_agent or settings.search_user_agent
        self._results = results or settings.search_results_per_claim
        self._extract_chars = extract_chars or settings.search_extract_chars
        self._sleep = sleep

    def search(self, query: str) -> list[SearchResult]:
        query = _clean_query(query)
        if not query:
            return []
        lang = detect_language(query)
        data = self._get_json(
            f"https://{lang}.wikipedia.org/w/api.php",
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrnamespace": 0,  # 일반 문서만 (토론/사용자 문서 제외)
                "gsrlimit": self._results,
                "prop": "extracts",
                "exintro": 1,  # 문서 도입부만
                "explaintext": 1,  # HTML 태그 없는 순수 텍스트
                "exchars": self._extract_chars,
                "exlimit": self._results,
                "format": "json",
                "formatversion": 2,
            },
        )
        pages = data.get("query", {}).get("pages", [])
        if not isinstance(pages, list):
            raise SearchBadResponseError("응답 형식이 예상과 다릅니다.")

        results: list[SearchResult] = []
        for page in sorted(pages, key=lambda p: p.get("index", 0)):
            title = page.get("title")
            extract = _clean_text(page.get("extract") or "")
            if not isinstance(title, str) or not extract:
                continue  # 본문이 없는 문서는 근거로 쓸 수 없다
            results.append(
                SearchResult(
                    title=title,
                    url=_page_url(lang, title),
                    snippet=extract,
                    source=f"wikipedia-{lang}",
                )
            )
        return results

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: SearchError = SearchUnavailableError("검색에 실패했습니다.")
        headers = {"User-Agent": self._user_agent, "Accept": "application/json"}
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            wait = 1.0
            try:
                response = self._fetch(url, params, headers, _TIMEOUT_SECONDS)
            except (OSError, http.client.HTTPException) as exc:  # 시간 초과, 연결 실패 등
                last_error = SearchUnavailableError("검색 서버에 연결하지 못했습니다.")
                logger.warning("검색 연결 오류 (시도 %d/%d): %s", attempt, _MAX_ATTEMPTS, type(exc).__name__)
            else:
                if response.status == 429:
                    last_error = SearchRateLimitedError("검색 요청 한도를 넘었습니다.")
                    wait = _retry_after_seconds(response.headers.get("retry-after"))
                elif response.status >= 500:
                    last_error = SearchUnavailableError("검색 서버 오류입니다.")
                elif response.status >= 400:
                    # 403(차단) 같은 거절은 재시도해도 소용없다.
                    logger.error("검색 요청 거절: HTTP %d", response.status)
                    raise SearchBadResponseError(f"검색 서버가 요청을 거절했습니다. (HTTP {response.status})")
                else:
                    return self._parse(response)
                logger.warning("검색 응답 오류 (시도 %d/%d): HTTP %d", attempt, _MAX_ATTEMPTS, response.status)

            if attempt < _MAX_ATTEMPTS:
                self._sleep(wait)
        raise last_error

    def _parse(self, response: HttpResponse) -> dict[str, Any]:
        try:
            data = json.loads(response.body.decode("utf-8"))
        except ValueError as exc:  # JSONDecodeError, UnicodeDecodeError 모두 ValueError의 하위 클래스
            raise SearchBadResponseError("검색 응답이 JSON이 아닙니다.") from exc
        if not isinstance(data, dict):
            raise SearchBadResponseError("검색 응답 형식이 예상과 다릅니다.")
        error = data.get("error")
        if error:
            code = error.get("code") if isinstance(error, dict) else None
            if code in ("ratelimited", "maxlag"):
                raise SearchRateLimitedError("검색 요청 한도를 넘었습니다.")
            logger.error("검색 API 오류 코드: %s", code)
            raise SearchBadResponseError("검색 API가 오류를 반환했습니다.")
        return data


def _retry_after_seconds(header: str | None) -> float:
    try:
        return min(max(float(header), 0.0), _MAX_RETRY_WAIT_SECONDS) if header else 1.0
    except ValueError:
        return 1.0  # Retry-After가 날짜 형식 등 숫자가 아닐 때


@lru_cache
def get_provider() -> SearchProvider:
    return WikipediaProvider()
