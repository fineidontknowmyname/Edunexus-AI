from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import decode_access_token
from backend.models.db import User, UserRole
from backend.models.schemas import TokenData

_bearer_scheme = HTTPBearer(auto_error=False)

CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)]
DbDep = Annotated[Session, Depends(get_db)]


def _get_token_data(credentials: CredentialsDep) -> TokenData:
    if credentials is None:
        print("[AUTH DEPENDENCY] Rejected request — no Authorization header present.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = decode_access_token(credentials.credentials)
    if token_data is None:
        print("[AUTH DEPENDENCY] Rejected request — token failed to decode/verify (invalid or expired).")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    print(f"[AUTH DEPENDENCY] Token decoded OK — user_id={token_data.user_id} role={token_data.role}")
    return token_data


def _get_current_user(token_data: Annotated[TokenData, Depends(_get_token_data)], db: DbDep) -> User:
    user = db.get(User, token_data.user_id)
    if user is None or not user.is_active:
        print(f"[AUTH DEPENDENCY] Rejected request — user_id={token_data.user_id} not found or inactive.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )
    return user


CurrentUser = Annotated[User, Depends(_get_current_user)]


def require_role(*roles: UserRole):
    def _check(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            print(
                f"[AUTH DEPENDENCY] Rejected request — user {current_user.id} has role "
                f"'{current_user.role.value}', requires one of {[r.value for r in roles]}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to: {[r.value for r in roles]}",
            )
        return current_user

    return _check


RequireStudent = Depends(require_role(UserRole.student))
RequireEducator = Depends(require_role(UserRole.educator))
RequireAdmin = Depends(require_role(UserRole.admin))
