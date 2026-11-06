"""호출 횟수 제한. 분석 1회에 Claude 비용이 들기 때문에 남용을 막는다.

- 분당 제한, 기록 조회 제한, 동시 실행 수는 서버 메모리로 처리한다. (짧은 시간 단위라 재시작해도 영향이 작다)
- 24시간 제한(IP별, 전체)은 DB(usage_events)에 기록한다. Render 무료 서버는 잠들었다 깨면
  메모리가 초기화되므로, 메모리만 쓰면 '쉬었다 다시 쓰기'로 하루 한도를 우회할 수 있다.
  DB를 쓸 수 없을 때는 메모리 카운터로 계속 제한한다. (제한 없이 열어 두지 않는다)
- IP 원본은 저장하지 않는다. 비밀 값(salt)을 섞은 HMAC 해시만 쓰고, 이 코드는 로그에도 IP를 남기지 않는다.
  (uvicorn 접속 로그와 호스팅 업체의 로그는 별개다)
- 중요(운영 실행 옵션): uvicorn은 기본으로 127.0.0.1에서 온 요청의 X-Forwarded-For를 믿고 클라이언트 주소를
  바꾼다. TRUSTED_PROXY_COUNT=0에서 이 변환이 켜져 있으면 헤더만 바꿔서 제한을 우회할 수 있다. (2026-11 실측:
  같은 사람이 헤더만 바꿔 5번 모두 통과) 그래서 운영에서는 항상 `uvicorn ... --no-proxy-headers`로 실행하고,
  주소 판별은 TRUSTED_PROXY_COUNT로만 한다. TRUSTED_PROXY_COUNT가 1 이상이면 헤더를 이 코드가 직접
  읽으므로 uvicorn의 설정과 무관하다.
- 한계: IP는 공유될 수 있고(학교, 회사) 바뀔 수도 있다. 전체 24시간 한도는 누군가 일부러 채워서
  다른 사용자의 사용을 막을 수 있다. 이 한도는 '비용의 상한'이 목적이라 그 점을 감수한다.
"""

import hashlib
import hmac
import ipaddress
import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import DatabaseNotConfiguredError, get_engine
from app.models import UsageEvent

logger = logging.getLogger(__name__)

_MINUTE = 60.0
_DAY = 24 * 3600.0
_MAX_TRACKED_KEYS = 10_000  # 메모리 사용을 제한하려고 추적하는 IP 수에 상한을 둔다
_ADVISORY_LOCK_KEY = 7_340_021  # 사용 기록 확인/추가를 한 번에 하나씩 처리하기 위한 DB 락 번호
_EVENT_RETENTION = timedelta(days=2)  # 24시간 집계에는 하루면 충분하다. 이틀 지난 기록은 지운다


# ------------------------------------------------------------------ 클라이언트 IP


def client_ip(request: Request, trusted_proxy_count: int | None = None) -> str:
    """요청을 보낸 클라이언트의 IP.

    trusted_proxy_count가 0이면 연결 상대의 주소를 그대로 쓴다. 1 이상이면 X-Forwarded-For의
    '오른쪽에서 N번째'를 쓴다. 맨 왼쪽 값은 클라이언트가 마음대로 써서 보낼 수 있으므로 믿지 않는다.
    (프록시가 자기가 본 주소를 오른쪽 끝에 덧붙이는 구조를 전제로 한다.)
    헤더가 기대와 다르면 연결 상대의 주소로 돌아간다. (프록시 주소 하나로 묶여 보수적으로 제한된다)
    """
    count = settings.trusted_proxy_count if trusted_proxy_count is None else trusted_proxy_count
    peer = request.client.host if request.client else "unknown"
    if count <= 0:
        return peer
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if len(parts) < count:
        return peer
    try:
        return str(ipaddress.ip_address(parts[-count]))
    except ValueError:
        return peer


def ip_hash(ip: str, salt: str) -> str:
    return hmac.new(salt.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ 안내 문구


def _seconds_until_free(oldest: datetime | None, now: datetime) -> float:
    """가장 오래된 사용 기록이 24시간 창에서 빠질 때까지 남은 초. 기록이 없으면(한도가 0일 때) 하루."""
    if oldest is None:
        return _DAY
    return (oldest + timedelta(days=1) - now).total_seconds()


def _format_wait(seconds: float) -> str:
    seconds = max(1, math.ceil(seconds))
    if seconds < 60:
        return f"{seconds}초"
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"{minutes}분"
    hours, rest = divmod(minutes, 60)
    return f"{hours}시간 {rest}분" if rest else f"{hours}시간"


def _limit_error(status: int, code: str, message: str, retry_after: float) -> AppError:
    return AppError(status, code, message, {"Retry-After": str(max(1, math.ceil(retry_after)))})


def _minute_error(retry_after: float) -> AppError:
    return _limit_error(
        429, "rate_limited", f"짧은 시간에 요청이 너무 많습니다. {_format_wait(retry_after)} 후 다시 시도해 주세요.", retry_after
    )


def _ip_day_error(limit: int, retry_after: float) -> AppError:
    return _limit_error(
        429,
        "daily_limit_reached",
        f"24시간 동안 사용할 수 있는 횟수({limit}회)를 모두 사용했습니다. 약 {_format_wait(retry_after)} 후 다시 시도해 주세요.",
        retry_after,
    )


def _global_day_error(retry_after: float) -> AppError:
    return _limit_error(
        429,
        "service_daily_limit",
        f"서비스의 하루 사용량 한도에 도달했습니다. 약 {_format_wait(retry_after)} 후 다시 이용해 주세요.",
        retry_after,
    )


# ------------------------------------------------------------------ 제한기


class RateLimiter:
    def __init__(
        self,
        *,
        ip_per_minute: int,
        ip_per_day: int,
        global_per_day: int,
        history_per_minute: int,
        max_concurrent: int,
        salt: str,
        session_factory: Callable[[], Session] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._ip_per_minute = ip_per_minute
        self._ip_per_day = ip_per_day
        self._global_per_day = global_per_day
        self._history_per_minute = history_per_minute
        self._salt = salt
        self._session_factory = session_factory or (lambda: Session(get_engine()))
        self._clock = clock

        self._lock = threading.Lock()
        self._minute: dict[str, deque[float]] = {}
        self._history: dict[str, deque[float]] = {}
        self._day_ip: dict[str, deque[float]] = {}  # DB를 쓸 수 없을 때를 위한 보조 카운터
        self._day_global: deque[float] = deque()
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))

    @classmethod
    def from_settings(cls) -> "RateLimiter":
        return cls(
            ip_per_minute=settings.rate_limit_ip_per_minute,
            ip_per_day=settings.rate_limit_ip_per_day,
            global_per_day=settings.rate_limit_global_per_day,
            history_per_minute=settings.rate_limit_history_per_minute,
            max_concurrent=settings.max_concurrent_analyses,
            salt=settings.rate_limit_salt,
        )

    def ip_hash(self, ip: str) -> str:
        return ip_hash(ip, self._salt)

    # ---- 메모리 슬라이딩 윈도우 (호출하는 쪽이 self._lock을 잡고 있어야 한다) ----

    def _purge(self, store: dict[str, deque[float]], window: float, now: float) -> None:
        for key in [k for k, dq in store.items() if not dq or dq[-1] <= now - window]:
            del store[key]
        if len(store) >= _MAX_TRACKED_KEYS:  # 아직도 많으면 오래 전에 들어온 것부터 10%를 버린다
            for key in list(store)[: _MAX_TRACKED_KEYS // 10]:
                del store[key]

    def _hit(self, store: dict[str, deque[float]], key: str, limit: int, window: float, now: float) -> float | None:
        """한도 안이면 기록하고 None, 넘으면 기록하지 않고 '몇 초 뒤에 다시'를 돌려준다."""
        if limit <= 0:  # 한도를 0으로 설정하면 모두 차단한다. (기록이 비어 있어 dq[0]을 읽으면 오류가 나므로 먼저 처리)
            return window
        dq = store.get(key)
        if dq is None:
            if len(store) >= _MAX_TRACKED_KEYS:
                self._purge(store, window, now)
            dq = store.setdefault(key, deque())
        while dq and dq[0] <= now - window:
            dq.popleft()
        if len(dq) >= limit:
            return dq[0] + window - now
        dq.append(now)
        return None

    # ---- 분석 요청 ----

    def admit_analysis(self, ip: str) -> None:
        """분석을 시작해도 되는지 확인하고 사용 1회를 기록한다. 안 되면 AppError(429)."""
        now = self._clock()
        key = self.ip_hash(ip)

        with self._lock:
            retry = self._hit(self._minute, key, self._ip_per_minute, _MINUTE, now)
        if retry is not None:
            raise _minute_error(retry)

        try:
            self._admit_daily_db(key)
        except (SQLAlchemyError, DatabaseNotConfiguredError, OSError) as exc:
            # 사용 기록 DB를 못 쓰면 메모리 카운터로라도 제한한다. (제한 없이 열어 두지 않는다)
            logger.warning("사용 기록 DB를 쓸 수 없어 메모리 카운터로 제한합니다: %s", type(exc).__name__)
            self._admit_daily_memory(key, now)
        else:
            with self._lock:  # DB가 정상이어도 보조 카운터를 함께 채워 둔다
                self._record_day_memory(key, now)

    def _admit_daily_db(self, key: str) -> None:
        with self._session_factory() as session:
            # 확인과 추가를 한 번에 하나씩 처리한다. 이게 없으면 동시에 들어온 요청들이 모두 '아직 한도
            # 안'이라고 보고 통과해서 한도를 넘는다. (트랜잭션이 끝나면 락도 풀린다)
            session.connection().execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            now = datetime.now(UTC)
            cutoff = now - timedelta(days=1)

            total, oldest = session.exec(
                select(func.count(), func.min(UsageEvent.created_at)).where(UsageEvent.created_at > cutoff)
            ).one()
            if total >= self._global_per_day:
                raise _global_day_error(_seconds_until_free(oldest, now))

            ip_total, ip_oldest = session.exec(
                select(func.count(), func.min(UsageEvent.created_at)).where(
                    UsageEvent.ip_hash == key, UsageEvent.created_at > cutoff
                )
            ).one()
            if ip_total >= self._ip_per_day:
                raise _ip_day_error(self._ip_per_day, _seconds_until_free(ip_oldest, now))

            session.add(UsageEvent(ip_hash=key))
            session.exec(delete(UsageEvent).where(UsageEvent.created_at < now - _EVENT_RETENTION))
            session.commit()

    def _record_day_memory(self, key: str, now: float) -> None:
        """보조 카운터에 사용 1회를 기록한다. 하루가 지난 값은 함께 정리해서 메모리가 계속 늘지 않게 한다."""
        while self._day_global and self._day_global[0] <= now - _DAY:
            self._day_global.popleft()
        self._day_global.append(now)

        dq = self._day_ip.get(key)
        if dq is None:
            if len(self._day_ip) >= _MAX_TRACKED_KEYS:
                self._purge(self._day_ip, _DAY, now)
            dq = self._day_ip.setdefault(key, deque())
        while dq and dq[0] <= now - _DAY:
            dq.popleft()
        dq.append(now)

    def _admit_daily_memory(self, key: str, now: float) -> None:
        with self._lock:
            while self._day_global and self._day_global[0] <= now - _DAY:
                self._day_global.popleft()
            if len(self._day_global) >= self._global_per_day:
                # 한도가 0이면 기록이 비어 있다. 그때는 '하루 뒤'로 안내한다.
                raise _global_day_error(self._day_global[0] + _DAY - now if self._day_global else _DAY)
            retry = self._hit(self._day_ip, key, self._ip_per_day, _DAY, now)  # 통과하면 IP 카운터에 기록된다
            if retry is not None:
                raise _ip_day_error(self._ip_per_day, retry)
            self._day_global.append(now)

    # ---- 동시 실행 ----

    @contextmanager
    def analysis_slot(self) -> Iterator[None]:
        """동시에 실행할 수 있는 분석 수를 제한한다. 가득 차면 기다리지 않고 바로 503."""
        if not self._slots.acquire(blocking=False):
            raise _limit_error(503, "busy", "지금 분석 요청이 몰려 있습니다. 잠시 후 다시 시도해 주세요.", 10)
        try:
            yield
        finally:
            self._slots.release()

    # ---- 기록 조회/삭제 ----

    def check_history(self, ip: str) -> None:
        now = self._clock()
        key = self.ip_hash(ip)
        with self._lock:
            retry = self._hit(self._history, key, self._history_per_minute, _MINUTE, now)
        if retry is not None:
            raise _minute_error(retry)


limiter = RateLimiter.from_settings()


def history_rate_limit(request: Request) -> None:
    """기록 조회/삭제, DB 확인 같은 가벼운 요청의 분당 제한 (FastAPI 의존성)."""
    limiter.check_history(client_ip(request))
