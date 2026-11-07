from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, Backup, BackupJob
from app.services import mysql_service, storage_service
from app.utils import now

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    del user
    from app.config import settings

    server = mysql_service.get_server_status()

    overview_dbs = []
    if server["connected"]:
        try:
            overview_dbs = mysql_service.get_database_overview(show_system=False)
        except Exception:
            overview_dbs = []

    total_tables = sum(item["table_count"] for item in overview_dbs)
    total_size = sum(item["total_size"] for item in overview_dbs)

    backups = db.query(Backup).filter(Backup.status == "success").filter(Backup.is_ephemeral.is_(False)).all()
    backup_count = len(backups)
    backup_bytes = sum(int(b.file_size) for b in backups)

    storage = storage_service.storage_status(db)

    recent_jobs = (
        db.query(BackupJob)
        .order_by(BackupJob.created_at.desc())
        .limit(5)
        .all()
    )
    recent_backups = (
        db.query(Backup)
        .filter(Backup.is_ephemeral.is_(False))
        .order_by(Backup.created_at.desc())
        .limit(5)
        .all()
    )
    recent_audit = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(5)
        .all()
    )

    activity_rows = (
        db.query(Backup.created_at)
        .filter(Backup.status == "success")
        .filter(Backup.is_ephemeral.is_(False))
        .filter(Backup.created_at >= now() - timedelta(days=13))
        .all()
    )
    activity_map: dict[str, int] = {}
    for (created_at,) in activity_rows:
        if created_at:
            key = created_at.strftime("%Y-%m-%d")
            activity_map[key] = activity_map.get(key, 0) + 1
    today = now().date()
    backup_activity = [
        {"date": (today - timedelta(days=offset)).isoformat(), "count": activity_map.get((today - timedelta(days=offset)).isoformat(), 0)}
        for offset in range(13, -1, -1)
    ]

    last_backup = recent_backups[0] if recent_backups else None

    return {
        "mysql": server,
        "totals": {
            "databases": len(overview_dbs),
            "tables": total_tables,
            "database_bytes": total_size,
            "backup_files": backup_count,
            "backup_bytes": backup_bytes,
        },
        "storage": storage,
        "databases": overview_dbs,
        "recent_jobs": [
            {
                "id": job.id,
                "database_name": job.database_name,
                "status": job.status,
                "requested_by": job.requested_by,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
            for job in recent_jobs
        ],
        "last_backup": {
            "filename": last_backup.filename,
            "database_name": last_backup.database_name,
            "file_size": int(last_backup.file_size),
            "created_at": last_backup.created_at.isoformat() if last_backup.created_at else None,
        }
        if last_backup
        else None,
        "backup_activity": backup_activity,
        "recent_audit": [
            {
                "action": entry.action,
                "actor": entry.actor,
                "status": entry.status,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
            }
            for entry in recent_audit
        ],
        "refresh_seconds": settings.MONITORING_REFRESH_SECONDS,
    }
