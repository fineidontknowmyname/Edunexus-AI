from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.security import create_access_token, hash_password, verify_password
from backend.models.db import Engagement, User, UserRole
from backend.services.context_service import check_staleness


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

    token = create_access_token(user_id=user.id, role=user.role.value)
    print(f"[AUTH SUCCESS] Login OK for user {user.id} ({user.email}, role={user.role.value})")

    return {
        "access_token": token,
        "token_type": "bearer",
    }


def get_user_by_id(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        print(f"[AUTH ERROR] get_user_by_id — user not found: {user_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user
