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

from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send


class TrailingSlashMiddleware:
    """Outermost ASGI middleware that normalises trailing slashes silently."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only touch HTTP/WebSocket requests that carry a non-root path.
        if scope["type"] not in ("http", "websocket") or scope.get("path") in (None, "", "/"):
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        alt: str = path.rstrip("/") if path.endswith("/") else path + "/"

        # Retrieve router routes from scope["app"], self.app, or traversing inner apps.
        routes = None
        for candidate in (scope.get("app"), self.app):
            curr = candidate
            while curr is not None:
                router = getattr(curr, "router", None)
                if router is not None and getattr(router, "routes", None):
                    routes = router.routes
                    break
                curr = getattr(curr, "app", None)
            if routes:
                break

        if not routes:
            await self.app(scope, receive, send)
            return

        def exists(p: str) -> bool:
            probe = {**scope, "path": p}
            return any(r.matches(probe)[0] in (Match.FULL, Match.PARTIAL) for r in routes)

        if not exists(path) and exists(alt):
            scope = dict(scope)
            scope["path"] = alt
            raw_path: bytes = scope.get("raw_path", path.encode())
            # Replace only the path portion of raw_path (keep query string if present).
            if b"?" in raw_path:
                _, qs = raw_path.split(b"?", 1)
                scope["raw_path"] = alt.encode() + b"?" + qs
            else:
                scope["raw_path"] = alt.encode()

        await self.app(scope, receive, send)
