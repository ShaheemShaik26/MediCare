from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, get_current_user, validate_session_csrf
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserOut
from app.services.auth_service import authenticate_user, create_access_token, create_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut)
def register_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")

    user = create_user(db, payload.email.lower(), payload.password, payload.full_name)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: UserLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    validate_session_csrf(request)
    user = authenticate_user(db, payload.email.lower(), payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")

    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_access_token(user),
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    validate_session_csrf(request)
    current_user.auth_token_version += 1
    db.commit()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
        secure=settings.secure_cookies,
        httponly=False,
        samesite="lax",
    )


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
