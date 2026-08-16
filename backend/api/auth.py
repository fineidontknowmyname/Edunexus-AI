from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import CurrentUser
from backend.core.database import get_db
from backend.models import schemas
from backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[Session, Depends(get_db)]


@router.post("/register", response_model=schemas.UserRead, status_code=201)
def register(payload: schemas.UserCreate, db: DbDep):
    return auth_service.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role,
    )


@router.post("/login", response_model=schemas.Token)
def login(payload: schemas.UserLogin, db: DbDep):
    return auth_service.login_user(
        db=db,
        email=payload.email,
        password=payload.password,
    )


@router.get("/me", response_model=schemas.UserRead)
def me(current_user: CurrentUser):
    return current_user
