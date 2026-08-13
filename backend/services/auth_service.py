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
    """
    Register a new platform user.

    Steps:
    1. Guard against duplicate emails.
    2. Hash the plain-text password.
    3. Persist the User record.
    4. For student accounts, create a linked Engagement record (streak=0).
    5. Commit and return a plain dict describing the new user.

    :raises HTTPException 400: if the email is already registered.
    """
    # 1 — Duplicate email guard
    existing = db.query(User).filter(User.email == email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with that email already exists.",
        )

    # 2 — Hash password
    hashed = hash_password(password)

    # 3 — Create and persist user
    user = User(
        email=email.lower(),
        hashed_password=hashed,
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()  # flush to get user.id without committing yet

    # 4 — Bootstrap Engagement record for student accounts
    if role == UserRole.student:
        engagement = Engagement(
            student_id=user.id,
            streak=0,
            longest_streak=0,
        )
        db.add(engagement)

    # 5 — Commit and return
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
    """
    Authenticate a user and return a signed JWT.

    Steps:
    1. Look up the user by email.
    2. Verify the submitted password against the stored hash.
    3. Generate and return a JWT access token.

    :raises HTTPException 401: if credentials are invalid or account is inactive.
    """
    # 1 — Fetch user
    user: User | None = db.query(User).filter(User.email == email.lower()).first()

    # 2 — Validate credentials
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

    # 3 — Issue JWT
    token = create_access_token(user_id=user.id, role=user.role.value)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


def get_user_by_id(db: Session, user_id: UUID) -> User:
    """
    Fetch a user by their UUID primary key.

    :raises HTTPException 404: if not found.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user
