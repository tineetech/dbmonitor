from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import client_ip, get_current_full_access, get_current_super_admin, require_csrf
from app.models import AppSetting
from app.schemas.schemas import SettingsUpdateRequest
from app.services import audit_service, storage_service

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

EDITABLE_KEYS = {
    "storage_warn_pct": "storage_warn_pct",
    "storage_critical_pct": "storage_critical_pct",
    "retention_days": "retention_days",
    "max_concurrent_backups": "max_concurrent_backups",
}


@router.get("")
def get_settings(db: Session = Depends(get_db), user: dict = Depends(get_current_full_access)):
    del user
    rows = {row.key: row.value for row in db.query(AppSetting).all()}
    return {
        "storage_warn_pct": int(rows.get("storage_warn_pct", settings.STORAGE_WARN_PCT)),
        "storage_critical_pct": int(rows.get("storage_critical_pct", settings.STORAGE_CRITICAL_PCT)),
        "retention_days": int(rows.get("retention_days", settings.BACKUP_RETENTION_DAYS)),
        "max_concurrent_backups": int(rows.get("max_concurrent_backups", settings.MAX_CONCURRENT_BACKUPS)),
        "show_system_databases": bool(settings.SHOW_SYSTEM_DATABASES),
        "connection": {
            "host": settings.DB_HOST,
            "port": settings.DB_PORT,
            "database": settings.DB_NAME,
            "username": settings.DB_USERNAME,
        },
        "backup": {
            "backup_dir": str(settings.backup_dir),
            "dump_binary": settings.resolve_dump_binary() if _dump_available() else None,
            "retention_days": int(rows.get("retention_days", settings.BACKUP_RETENTION_DAYS)),
        },
    }


def _dump_available() -> bool:
    try:
        settings.resolve_dump_binary()
        return True
    except FileNotFoundError:
        return False


@router.post("")
def update_settings(
    payload: SettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_super_admin),
    _csrf: dict = Depends(require_csrf),
):
    changes = payload.model_dump(exclude_unset=True)
    applied: dict[str, str] = {}
    for key, value in changes.items():
        if key in EDITABLE_KEYS:
            storage_service.set_setting(db, EDITABLE_KEYS[key], str(int(value)))
            applied[key] = str(int(value))
    if applied:
        audit_service.log_event(
            db,
            actor=user["username"],
            action="settings_updated",
            status="success",
            ip_address=client_ip(request),
            detail=", ".join(f"{key}={value}" for key, value in applied.items()),
        )
    return {"applied": applied}

