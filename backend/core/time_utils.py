from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any


def is_valid_timezone(name: str | None) -> bool:
    """Returns True if name is a valid IANA timezone string."""
    if not name or not isinstance(name, str):
        return False
    clean_name = name.strip()
    if not clean_name:
        return False
    try:
        ZoneInfo(clean_name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError, Exception):
        return False


def local_today(tz_name: str | None, now: datetime | None = None) -> date:
    """
    Returns the current calendar date in the specified timezone.
    'now' is an optional timezone-aware UTC datetime (primarily used for unit testing).
    Defaults to datetime.now(timezone.utc).
    Falls back to UTC date if tz_name is None, empty, or invalid.
    """
    current_utc = now if now is not None else datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)

    if tz_name and is_valid_timezone(tz_name):
        try:
            return current_utc.astimezone(ZoneInfo(tz_name.strip())).date()
        except Exception:
            return current_utc.astimezone(timezone.utc).date()

    return current_utc.astimezone(timezone.utc).date()


def effective_streak(
    current_streak: int, last_interaction_date: date | None, today: date
) -> int:
    """
    Computes effective streak on read.
    - If last_interaction_date is None: return 0
    - If last_interaction_date > today (clock moved backwards / timezone shift): return current_streak
    - If (today - last_interaction_date).days <= 1: return current_streak (today or yesterday)
    - Otherwise (missed 2+ days): return 0
    """
    if last_interaction_date is None:
        return 0
    if last_interaction_date > today:
        return current_streak
    if (today - last_interaction_date).days <= 1:
        return current_streak
    return 0


def capture_client_timezone(user: Any, header_value: str | None) -> bool:
    """
    Captures the client's timezone from request header if valid and different.
    Must NOT commit and must NOT open its own transaction.
    """
    if not header_value or not is_valid_timezone(header_value):
        return False
    clean_tz = header_value.strip()
    if getattr(user, "timezone", None) != clean_tz:
        user.timezone = clean_tz
        return True
    return False
