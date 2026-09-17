import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser
from backend.core import cookies
from backend.core.database import get_db
from backend.core.rate_limit import rate_limit
from backend.core.security import create_access_token
from backend.models import schemas
from backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]

RegisterRateLimit = Depends(rate_limit("auth-register", max_requests=5, window_seconds=60))
LoginRateLimit = Depends(rate_limit("auth-login", max_requests=10, window_seconds=60))
RefreshRateLimit = Depends(rate_limit("auth-refresh", max_requests=20, window_seconds=60))


@router.post("/register", response_model=schemas.UserRead, status_code=201, dependencies=[RegisterRateLimit])
def register(payload: schemas.UserCreate, db: DbDep):
    return auth_service.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )


@router.post("/login", response_model=schemas.LoginResponse, dependencies=[LoginRateLimit])
def login(payload: schemas.UserLogin, db: DbDep, response: Response):
    result = auth_service.login_user(db=db, email=payload.email, password=payload.password)
    user = result["user"]
    csrf_token = secrets.token_urlsafe(32)
    cookies.set_auth_cookies(
        response, result["access_token"], result["refresh_token"], csrf_token, user.role.value
    )
    return {"user": user}


@router.post("/refresh", response_model=schemas.LoginResponse, dependencies=[RefreshRateLimit])
def refresh(request: Request, response: Response, db: DbDep):
    raw_refresh = request.cookies.get(cookies.REFRESH_COOKIE)
    if raw_refresh is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active session.")

    user, new_refresh = auth_service.rotate_refresh_token(db, raw_refresh)
    new_access = create_access_token(user_id=user.id, role=user.role.value)
    csrf_token = secrets.token_urlsafe(32)
    cookies.set_auth_cookies(response, new_access, new_refresh, csrf_token, user.role.value)
    return {"user": user}


@router.post("/logout", response_model=schemas.MessageResponse)
def logout(request: Request, response: Response, db: DbDep):
    raw_refresh = request.cookies.get(cookies.REFRESH_COOKIE)
    if raw_refresh is not None:
        auth_service.revoke_refresh_token(db, raw_refresh)
    cookies.clear_auth_cookies(response)
    return {"message": "Logged out."}


@router.get("/me", response_model=schemas.UserRead)
def me(current_user: CurrentUser):
    return current_user


@router.patch("/me", response_model=schemas.UserRead)
def update_me(payload: schemas.ProfileUpdate, db: DbDep, current_user: CurrentUser):
    return auth_service.update_profile(db=db, user=current_user, full_name=payload.full_name)


@router.post("/change-password", response_model=schemas.MessageResponse)
def change_password(payload: schemas.ChangePasswordRequest, db: DbDep, current_user: CurrentUser):
    auth_service.change_password(
        db=db,
        user=current_user,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    return {"message": "Password changed successfully."}
