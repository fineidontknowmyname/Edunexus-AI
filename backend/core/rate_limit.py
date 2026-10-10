import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from backend.core.cookies import ACCESS_COOKIE
from backend.core.security import decode_access_token

_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _client_key(request: Request) -> str:
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        data = decode_access_token(token)
        if data is not None and data.user_id is not None:
            return f"user:{data.user_id}"
    return f"ip:{_client_ip(request)}"


def _enforce(key: str, client: str, max_requests: int, window_seconds: int, record: bool) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        timestamps = _buckets[(key, client)]
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            retry_after = max(1, int(timestamps[0] + window_seconds - now))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. Please wait {retry_after} seconds and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        if record:
            timestamps.append(now)


def hit(key: str, client: str, max_requests: int, window_seconds: int) -> None:
    _enforce(key, client, max_requests, window_seconds, record=True)


def check(key: str, client: str, max_requests: int, window_seconds: int) -> None:
    _enforce(key, client, max_requests, window_seconds, record=False)


def rate_limit(key: str, max_requests: int, window_seconds: int = 60):
    def _check(request: Request) -> None:
        hit(key, _client_key(request), max_requests, window_seconds)

    return _check


def reset_rate_limits() -> None:
    with _lock:
        _buckets.clear()
