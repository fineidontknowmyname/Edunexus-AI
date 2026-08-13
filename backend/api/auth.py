from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser
from backend.core.database import get_db
from backend.models import schemas
from backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=schemas.UserRead,
    status_code=201,
    summary="Register a new user account",
)
def register(payload: schemas.UserCreate, db: DbDep):
    """
    Create a new student or educator account.

    - Validates that the email is not already registered.
    - Hashes the password with bcrypt.
    - Creates a linked **Engagement** record for student accounts (streak = 0).
    - Returns the new user object (no password field).
    """
    return auth_service.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=schemas.Token,
    summary="Login and retrieve a JWT access token",
)
def login(payload: schemas.UserLogin, db: DbDep):
    """
    Authenticate with email + password.

    Returns a signed JWT (`access_token`) in Bearer format.
    """
    return auth_service.login_user(
        db=db,
        email=payload.email,
        password=payload.password,
    )


# ── GET /auth/me ──────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=schemas.UserRead,
    summary="Get the currently authenticated user",
)
def me(current_user: CurrentUser):
    """
    Returns the profile of the user identified by the Bearer token.

    Requires a valid JWT in the `Authorization: Bearer <token>` header.
    """
    return current_user
