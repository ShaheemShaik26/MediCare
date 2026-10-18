from __future__ import annotations

import secrets

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
SESSION_COOKIE_NAME = "medicare_session"
CSRF_COOKIE_NAME = "medicare_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def validate_session_csrf(request: Request) -> None:
    if not request.cookies.get(SESSION_COOKIE_NAME) or request.method in {"GET", "HEAD", "OPTIONS"}:
        return

    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    csrf_header = request.headers.get(CSRF_HEADER_NAME, "")
    if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    validate_session_csrf(request)

    token = session_token or (credentials.credentials if credentials else None)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id = int(payload.get("sub", ""))
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if payload.get("ver", 0) != user.auth_token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    return user
