import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.core.cookies import CSRF_COOKIE

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_EXEMPT_PATHS = {"/api/v1/auth/login", "/api/v1/auth/register"}
_CSRF_HEADER = "X-CSRF-Token"


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if (
            request.method in _SAFE_METHODS
            or request.url.path in _EXEMPT_PATHS
            or "authorization" in request.headers
        ):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE)
        header_token = request.headers.get(_CSRF_HEADER)
        if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
            return JSONResponse(
                {"detail": "CSRF token missing or invalid."},
                status_code=403,
            )

        return await call_next(request)
