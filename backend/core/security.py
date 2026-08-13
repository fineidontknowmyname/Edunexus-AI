from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.core.config import get_settings
from backend.models.schemas import TokenData

settings = get_settings()

# ── Password hashing ──────────────────────────────────────────────────────────
# bcrypt is the recommended algorithm; auto_deprecated keeps older hashes
# working while silently upgrading them on next login.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of *plain_password*."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*."""
    return _pwd_context.verify(plain_password, hashed_password)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: UUID, role: str) -> str:
    """
    Create a signed JWT containing *user_id* and *role*.

    Expiry is controlled by ``settings.jwt_expire_hours``.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenData | None:
    """
    Decode and validate *token*.

    Returns a :class:`TokenData` instance on success, or ``None`` if the
    token is invalid / expired.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        role: str | None = payload.get("role")
        if user_id is None:
            return None
        return TokenData(user_id=UUID(user_id), role=role)
    except JWTError:
        return None
