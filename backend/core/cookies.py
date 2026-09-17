from fastapi import Response

from backend.core.config import get_settings

ACCESS_COOKIE = "edunexus_access"
REFRESH_COOKIE = "edunexus_refresh"
CSRF_COOKIE = "edunexus_csrf"
ROLE_COOKIE = "edunexus_role"
AUTH_PATH = "/api/v1/auth"

settings = get_settings()


def _cookie_attrs() -> dict:
    if settings.environment.lower() == "production":
        return {"secure": True, "samesite": "none"}
    return {"secure": False, "samesite": "lax"}


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    csrf_token: str,
    role: str,
) -> None:
    attrs = _cookie_attrs()
    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 86400

    response.set_cookie(
        ACCESS_COOKIE, access_token, max_age=access_max_age, path="/", httponly=True, **attrs
    )
    response.set_cookie(
        REFRESH_COOKIE, refresh_token, max_age=refresh_max_age, path=AUTH_PATH, httponly=True, **attrs
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=refresh_max_age, path="/", httponly=False, **attrs
    )
    response.set_cookie(
        ROLE_COOKIE, role, max_age=refresh_max_age, path="/", httponly=False, **attrs
    )


def clear_auth_cookies(response: Response) -> None:
    attrs = _cookie_attrs()
    response.delete_cookie(ACCESS_COOKIE, path="/", **attrs)
    response.delete_cookie(REFRESH_COOKIE, path=AUTH_PATH, **attrs)
    response.delete_cookie(CSRF_COOKIE, path="/", **attrs)
    response.delete_cookie(ROLE_COOKIE, path="/", **attrs)
