from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import security
from app.config import settings
from app.database import get_db
from app.dependencies import client_ip, get_current_user, get_session_data, require_csrf
from app.models import AdminUser
from app.schemas.schemas import LoginRequest
from app.services import audit_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
    session: dict = Depends(require_csrf),
):
    ip = client_ip(request)
    limiter_key = f"{ip}|{payload.username.lower()}"
    if not security.login_rate_limiter.is_allowed(limiter_key):
        audit_service.log_event(
            db, actor=payload.username, action="login_failed", status="rate_limited",
            ip_address=ip, detail="Too many failed attempts",
        )
        return JSONResponse(
            {"detail": "Too many failed attempts. Try again in a few minutes."},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = db.query(AdminUser).filter(AdminUser.username == payload.username).first()
    if not user or not user.is_active or not security.verify_password(user.password_hash, payload.password):
        security.login_rate_limiter.record_failure(limiter_key)
        audit_service.log_event(
            db, actor=payload.username, action="login_failed", status="failed",
            ip_address=ip, detail="Invalid credentials",
        )
        return JSONResponse({"detail": "Invalid username or password"}, status_code=status.HTTP_401_UNAUTHORIZED)

    security.login_rate_limiter.reset(limiter_key)

    from app.utils import now

    user.last_login_at = now()
    user.last_login_ip = ip
    db.commit()

    token, csrf = security.create_session(user.id, user.username, user.role)
    audit_service.log_event(
        db, actor=user.username, action="login_success", status="success", ip_address=ip,
    )

    response = JSONResponse({"detail": "Login successful", "username": user.username, "role": user.role})
    response.set_cookie(
        security.SESSION_COOKIE,
        token,
        max_age=settings.SESSION_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )
    return response


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    session: dict = Depends(require_csrf),
):
    response = JSONResponse({"detail": "Logged out"})
    response.delete_cookie(security.SESSION_COOKIE, path="/")
    audit_service.log_event(
        db, actor=user["username"], action="logout", status="success", ip_address=client_ip(request),
    )
    return response


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return {"id": user["id"], "username": user["username"], "role": user["role"]}
