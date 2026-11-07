from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import security
from app.config import PROJECT_ROOT, settings
from app.dependencies import FULL_ACCESS_ROLES, get_session_data

router = APIRouter()
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "app" / "templates"))


def page_context(request: Request) -> Optional[dict]:
    session = get_session_data(request)
    if not session or int(session.get("uid", 0)) <= 0:
        return None
    return {
        "user": {"id": session.get("uid"), "username": session.get("sub"), "role": session.get("role")},
        "csrf_token": session.get("csrf"),
        "full_access": session.get("role") in FULL_ACCESS_ROLES,
    }


def render(request: Request, template: str, context: Optional[dict] = None, allow_viewer: bool = False):
    base = page_context(request)
    if not base:
        return RedirectResponse(url="/login", status_code=303)
    if not allow_viewer and not base["full_access"]:
        return RedirectResponse(url="/dashboard", status_code=303)
    payload = {"request": request, **base, **(context or {})}
    return templates.TemplateResponse(request, template, payload)


@router.get("/login")
def login_page(request: Request):
    if page_context(request):
        return RedirectResponse(url="/dashboard", status_code=303)
    token, csrf = security.create_anonymous_session()
    response = templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "csrf_token": csrf, "user": None},
    )
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


@router.get("/")
def index():
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard")
def dashboard_page(request: Request):
    return render(request, "dashboard.html", allow_viewer=True)


@router.get("/databases")
def databases_page(request: Request):
    return render(request, "databases.html")


@router.get("/databases/{name}")
def database_detail_page(request: Request, name: str):
    return render(request, "database_detail.html", {"database_name": name})


@router.get("/backups")
def backups_page(request: Request):
    return render(request, "backups.html", allow_viewer=True)


@router.get("/backups/{backup_id}")
def backup_detail_page(request: Request, backup_id: int):
    return render(request, "backup_detail.html", {"backup_id": backup_id}, allow_viewer=True)


@router.get("/monitoring")
def monitoring_page(request: Request):
    return render(request, "monitoring.html")


@router.get("/schedules")
def schedules_page(request: Request):
    return render(request, "schedules.html")


@router.get("/settings")
def settings_page(request: Request):
    return render(request, "settings.html")


@router.get("/audit-logs")
def audit_logs_page(request: Request):
    return render(request, "audit_logs.html")
