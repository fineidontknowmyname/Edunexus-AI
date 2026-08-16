from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.core.security import create_access_token, hash_password, verify_password
from backend.models.db import Engagement, User, UserRole


def register_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.student,
) -> dict:
    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing:
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

    db.commit()
    db.refresh(user)

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


def login_user(db: Session, email: str, password: str) -> dict:
    user: User | None = db.query(User).filter(User.email == email.lower()).first()

    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated. Contact support.",
        )

    token = create_access_token(user_id=user.id, role=user.role.value)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


def get_user_by_id(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user
