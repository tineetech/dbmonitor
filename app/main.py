from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import init_db
from app.routers import (
    api_audit,
    api_auth,
    api_backups,
    api_dashboard,
    api_databases,
    api_monitoring,
    api_schedules,
    api_settings,
    pages,
)

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"cache-control", b"no-store"),
                    (b"content-security-policy", b"default-src 'self'; script-src 'self' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"),
                ]
                existing = {name.lower() for name, _ in headers}
                for name, value in extra:
                    if name not in existing:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _error_page(request: Request, status_code: int, message: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": status_code, "message": message, "user": None, "csrf_token": ""},
        status_code=status_code,
    )


async def lifespan(app: FastAPI):
    init_db()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="DB Monitor & Backup Manager",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    app.include_router(pages.router)
    app.include_router(api_auth.router)
    app.include_router(api_dashboard.router)
    app.include_router(api_databases.router)
    app.include_router(api_backups.router)
    app.include_router(api_monitoring.router)
    app.include_router(api_schedules.router)
    app.include_router(api_settings.router)
    app.include_router(api_audit.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return _error_page(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            errors = [{"loc": list(err.get("loc", [])), "msg": err.get("msg", "")} for err in exc.errors()]
            return JSONResponse({"detail": "Validation error", "errors": errors}, status_code=422)
        return JSONResponse({"detail": "Validation error"}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Internal server error"}, status_code=500)
        return _error_page(request, 500, "Terjadi kesalahan internal")

    return app


app = create_app()
