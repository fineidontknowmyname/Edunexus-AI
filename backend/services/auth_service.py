from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from backend.models.db import Engagement, RefreshToken, User, UserRole
from backend.services.context_service import check_staleness

settings = get_settings()


def register_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.student,
) -> dict:
    print(f"[AUTH] Register attempt: email={email} role={role.value}")

    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing:
        print(f"[AUTH ERROR] Register rejected — email already registered: {email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with that email already exists.",
        )

    hashed = hash_password(password)

    user = User(
        email=email.lower(),
        hashed_password=hashed,
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()

    if role == UserRole.student:
        engagement = Engagement(
            student_id=user.id,
            current_streak=0,
            longest_streak=0,
        )
        db.add(engagement)
        print(f"[AUTH] Bootstrapped Engagement row for student {user.id}")

    db.commit()
    db.refresh(user)

    print(f"[AUTH SUCCESS] Registered user {user.id} ({user.email}, role={user.role.value})")

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


def _create_refresh_token(db: Session, user_id: UUID) -> str:
    raw = generate_refresh_token()
    db.add(
        RefreshToken(
            token_hash=hash_refresh_token(raw),
            expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
            user_id=user_id,
        )
    )
    db.commit()
    return raw


def _revoke_all_for_user(db: Session, user_id: UUID) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    ).update({RefreshToken.revoked_at: datetime.utcnow()})
    db.commit()
    print(f"[AUTH] Revoked all active refresh tokens for user {user_id}")


def login_user(db: Session, email: str, password: str) -> dict:
    print(f"[AUTH] Login attempt: email={email}")

    user: User | None = db.query(User).filter(User.email == email.lower()).first()

    if user is None or not verify_password(password, user.hashed_password):
        print(f"[AUTH ERROR] Login rejected — invalid credentials for email={email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        print(f"[AUTH ERROR] Login rejected — account deactivated: user_id={user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated. Contact support.",
        )

    if user.role == UserRole.student:
        check_staleness(db, user.id)

    access_token = create_access_token(user_id=user.id, role=user.role.value)
    refresh_token = _create_refresh_token(db, user.id)
    print(f"[AUTH SUCCESS] Login OK for user {user.id} ({user.email}, role={user.role.value})")

    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[User, str]:
    token_hash = hash_refresh_token(raw_token)
    row: RefreshToken | None = (
        db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    )

    if row is None or row.expires_at < datetime.utcnow():
        print("[AUTH ERROR] Refresh rejected — token missing or expired")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")

    if row.revoked_at is not None:
        print(f"[AUTH ERROR] Refresh token reuse detected for user {row.user_id} — revoking all sessions")
        _revoke_all_for_user(db, row.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalidated, please log in again.",
        )

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        print(f"[AUTH ERROR] Refresh rejected — user {row.user_id} not found or inactive")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session.")

    row.revoked_at = datetime.utcnow()
    db.commit()
    new_raw = _create_refresh_token(db, user.id)
    print(f"[AUTH SUCCESS] Refresh OK for user {user.id}")
    return user, new_raw


def revoke_refresh_token(db: Session, raw_token: str) -> None:
    token_hash = hash_refresh_token(raw_token)
    row: RefreshToken | None = (
        db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.utcnow()
        db.commit()
        print(f"[AUTH] Refresh token revoked for user {row.user_id} (logout)")


def update_profile(db: Session, user: User, full_name: str) -> User:
    print(f"[AUTH] Profile update: user={user.id} full_name={full_name!r}")
    user.full_name = full_name
    db.commit()
    db.refresh(user)
    print(f"[AUTH SUCCESS] Profile updated for user {user.id}")
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    print(f"[AUTH] Change-password attempt: user={user.id}")

    if not verify_password(current_password, user.hashed_password):
        print(f"[AUTH ERROR] Change-password rejected — current password incorrect: user={user.id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    user.hashed_password = hash_password(new_password)
    db.commit()
    print(f"[AUTH SUCCESS] Password changed for user {user.id}")


def get_user_by_id(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        print(f"[AUTH ERROR] get_user_by_id — user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user
