"""
Tests for TrailingSlashMiddleware.

Uses a self-contained FastAPI application that mirrors the relevant route
patterns from the real EduNexus API so the tests stay fast and do not require
a database or any environment variables.

Covered scenarios
-----------------
1. ``POST /auth/register``  → registered without trailing slash; both
   ``/auth/register`` and ``/auth/register/`` must reach the handler with
   status 200 and no 307 redirect.
2. ``GET /classes/`` → registered *with* trailing slash; both ``/classes/``
   and ``/classes`` must reach the handler with status 200 and no 307.
3. A completely unknown path (``/unknown/path``) is left untouched and returns
   404 as normal.
4. ``scope['raw_path']`` is also rewritten when the middleware normalises a
   path (sanity-checked via a small ASGI test helper).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.trailing_slash import TrailingSlashMiddleware


# ---------------------------------------------------------------------------
# Minimal test application
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    """Return a small FastAPI app that mirrors the relevant EduNexus routes."""
    app = FastAPI()

    # Route declared WITHOUT trailing slash (mirrors /api/v1/auth/register).
    @app.post("/auth/register")
    def register():
        return {"route": "register"}

    # Route declared WITH trailing slash (mirrors /api/v1/classes/).
    @app.get("/classes/")
    def list_classes():
        return {"route": "classes"}

    # Add the middleware as the outermost layer (last add_middleware call).
    app.add_middleware(TrailingSlashMiddleware)

    return app


# Build once for the whole module.
_app = _make_app()
_client = TestClient(_app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_no_redirect(response) -> None:
    """Fail if the response is any 3xx redirect."""
    assert response.status_code not in range(300, 400), (
        f"Unexpected redirect {response.status_code} → {response.headers.get('location')}"
    )


# ---------------------------------------------------------------------------
# /auth/register  (route declared WITHOUT trailing slash)
# ---------------------------------------------------------------------------

class TestAuthRegister:
    """Both /auth/register and /auth/register/ must reach the handler."""

    def test_exact_path_returns_200(self):
        r = _client.post("/auth/register", json={})
        _assert_no_redirect(r)
        assert r.status_code == 200
        assert r.json() == {"route": "register"}

    def test_trailing_slash_variant_returns_200_no_307(self):
        r = _client.post("/auth/register/", json={})
        _assert_no_redirect(r)
        assert r.status_code == 200, (
            f"Expected 200 from /auth/register/, got {r.status_code}"
        )
        assert r.json() == {"route": "register"}


# ---------------------------------------------------------------------------
# /classes/  (route declared WITH trailing slash)
# ---------------------------------------------------------------------------

class TestClasses:
    """Both /classes/ and /classes must reach the handler."""

    def test_exact_path_with_slash_returns_200(self):
        r = _client.get("/classes/")
        _assert_no_redirect(r)
        assert r.status_code == 200
        assert r.json() == {"route": "classes"}

    def test_no_trailing_slash_variant_returns_200_no_307(self):
        r = _client.get("/classes")
        _assert_no_redirect(r)
        assert r.status_code == 200, (
            f"Expected 200 from /classes, got {r.status_code}"
        )
        assert r.json() == {"route": "classes"}


# ---------------------------------------------------------------------------
# Unknown paths are not affected
# ---------------------------------------------------------------------------

class TestUnknownPath:
    """Paths that have no matching route in either slash form return 404."""

    def test_unknown_path_returns_404(self):
        r = _client.get("/unknown/path")
        assert r.status_code == 404

    def test_unknown_path_with_slash_returns_404(self):
        r = _client.get("/unknown/path/")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# raw_path rewriting (ASGI-level check)
# ---------------------------------------------------------------------------

class TestRawPathRewriting:
    """
    Verify that scope['raw_path'] is also updated when the middleware rewrites
    the path.  We place a tiny ASGI spy *between* TrailingSlashMiddleware and
    the FastAPI app so it observes the already-rewritten scope.
    """

    def test_raw_path_is_rewritten_for_slash_variant(self):
        captured: list[dict] = []

        inner_app = FastAPI()

        @inner_app.get("/items/")
        def get_items():
            return {"ok": True}

        # Build the spy as a standalone ASGI callable that wraps inner_app.
        async def spy_asgi(scope, receive, send):
            if scope["type"] == "http":
                captured.append(
                    {
                        "path": scope.get("path"),
                        "raw_path": scope.get("raw_path"),
                    }
                )
            await inner_app(scope, receive, send)

        # TrailingSlashMiddleware wraps the spy; the spy wraps inner_app.
        # The middleware's self.app is spy_asgi, which has no .router,
        # so we need it to inspect inner_app's router.  We attach it manually.
        from backend.core.trailing_slash import TrailingSlashMiddleware

        # Give the spy a .router reference so the middleware can probe routes.
        spy_asgi.router = inner_app.router  # type: ignore[attr-defined]

        wrapped = TrailingSlashMiddleware(spy_asgi)

        client = TestClient(wrapped, raise_server_exceptions=True)
        r = client.get("/items")  # no trailing slash → should be rewritten to /items/
        assert r.status_code == 200

        # The spy should have seen the rewritten path.
        assert captured, "Spy was never called"
        last = captured[-1]
        assert last["path"] == "/items/", f"path not rewritten: {last['path']!r}"
        assert last["raw_path"] == b"/items/", (
            f"raw_path not rewritten: {last['raw_path']!r}"
        )
