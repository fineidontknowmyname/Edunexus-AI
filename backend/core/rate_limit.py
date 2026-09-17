import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_buckets: dict[tuple[str, str], list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(key: str, max_requests: int, window_seconds: int = 60):
    def _check(request: Request) -> None:
        client_ip = _client_ip(request)
        bucket_key = (key, client_ip)
        now = time.time()
        cutoff = now - window_seconds

        timestamps = _buckets[bucket_key]
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= max_requests:
            print(
                f"[RATE LIMIT] '{key}' blocked ip={client_ip} "
                f"({len(timestamps)}/{max_requests} in {window_seconds}s)"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
            )

        timestamps.append(now)

    return _check
