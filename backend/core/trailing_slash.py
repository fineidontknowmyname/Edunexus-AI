"""
Pure-ASGI middleware that makes trailing slashes transparent.

For every incoming HTTP request, if the router does **not** fully match the
requested path but *does* fully match the path with a trailing slash added or
removed, ``scope['path']`` (and ``scope['raw_path']``) are rewritten to the
matching form **before** the request is forwarded downstream.

No 3xx redirect is issued – the client always receives a 2xx (or whatever the
handler returns) at the URL it originally requested.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    pass


class TrailingSlashMiddleware:
    """Outermost ASGI middleware that normalises trailing slashes silently."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only touch HTTP/HTTPS requests that carry a path.
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Ask the router whether the current path is a full match.
        # ``self.app`` is the Starlette/FastAPI application; its ``router``
        # attribute holds the registered routes.
        router = getattr(self.app, "router", None)
        if router is None or not path:
            await self.app(scope, receive, send)
            return

        # Build a minimal probe scope to check route matches without
        # mutating the real scope yet.
        def _matches(test_path: str) -> bool:
            probe = {**scope, "path": test_path}
            match, _ = router.routes and _best_match(router, probe) or (Match.NONE, None)
            return match == Match.FULL

        def _best_match(rtr, probe_scope):
            """Return the best (match, child) across all routes."""
            best = Match.NONE
            for route in rtr.routes:
                m, _ = route.matches(probe_scope)
                if m == Match.FULL:
                    return Match.FULL, route
                if m == Match.PARTIAL:
                    best = Match.PARTIAL
            return best, None

        current_matches = _matches(path)

        if not current_matches:
            # Try the opposite slash form.
            if path.endswith("/"):
                alt_path = path.rstrip("/") or "/"
            else:
                alt_path = path + "/"

            if _matches(alt_path):
                # Rewrite path in scope so downstream sees the canonical form.
                scope = dict(scope)
                scope["path"] = alt_path
                raw_path: bytes = scope.get("raw_path", path.encode())
                # Replace only the path portion of raw_path (keep query string).
                # raw_path may include the query string separated by b"?".
                if b"?" in raw_path:
                    _, qs = raw_path.split(b"?", 1)
                    scope["raw_path"] = alt_path.encode() + b"?" + qs
                else:
                    scope["raw_path"] = alt_path.encode()

        await self.app(scope, receive, send)
