from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import security
from app.database import get_db
from app.models import AdminUser

FULL_ACCESS_ROLES = frozenset({"super_admin", "admin"})
VIEWER_ROLE = "viewer"


def get_session_data(request: Request) -> Optional[dict]:
    token = request.cookies.get(security.SESSION_COOKIE)
    return security.load_session(token)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> dict:
    session = get_session_data(request)
    if not session or int(session.get("uid", 0)) <= 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.get(AdminUser, int(session["uid"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "csrf": session.get("csrf"),
    }


def get_current_full_access(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in FULL_ACCESS_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    return user


def get_current_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    return user


def require_csrf(request: Request) -> dict:
    session = get_session_data(request)
    if not session:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing session")
    candidate = request.headers.get("x-csrf-token") or request.headers.get("x-xsrf-token")
    if not security.csrf_valid(session, candidate):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")
    return session


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
