import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppSetting, Backup


def get_int_setting(db: Session, key: str, default: int) -> int:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value=str(value))
        db.add(row)
    else:
        row.value = str(value)
    db.commit()


def disk_usage(path: Path) -> dict:
    usage = shutil.disk_usage(str(path))
    total, used, free = int(usage.total), int(usage.used), int(usage.free)
    percent = round(used / total * 100, 2) if total else 0.0
    return {"total": total, "used": used, "free": free, "percent": percent}


def backup_storage_stats(db: Session) -> dict:
    rows = db.query(Backup).filter(Backup.status == "success").filter(Backup.is_ephemeral.is_(False)).all()
    count = len(rows)
    total_bytes = sum(int(row.file_size) for row in rows)
    missing = 0
    backup_dir = settings.backup_dir
    for row in rows:
        candidate = safe_backup_path(row.relative_path or row.filename)
        if candidate is None or not candidate.exists():
            missing += 1
    return {
        "file_count": count,
        "total_bytes": total_bytes,
        "missing_files": missing,
        "backup_dir": str(backup_dir),
    }


def safe_backup_path(filename: str) -> Optional[Path]:
    if not filename:
        return None
    cleaned = filename.strip()
    if cleaned in (".", "..") or cleaned != Path(cleaned).name:
        return None
    base = settings.backup_dir.resolve()
    candidate = (base / cleaned).resolve()
    if candidate.parent == base:
        return candidate
    return None


def storage_status(db: Session) -> dict:
    usage = disk_usage(settings.backup_dir)
    warn_pct = get_int_setting(db, "storage_warn_pct", settings.STORAGE_WARN_PCT)
    critical_pct = get_int_setting(db, "storage_critical_pct", settings.STORAGE_CRITICAL_PCT)
    used_pct = usage["percent"]
    if used_pct >= critical_pct:
        level = "critical"
    elif used_pct >= warn_pct:
        level = "warning"
    else:
        level = "ok"
    stats = backup_storage_stats(db)
    return {
        "disk": usage,
        "level": level,
        "warn_pct": warn_pct,
        "critical_pct": critical_pct,
        "backup_storage": stats,
    }
