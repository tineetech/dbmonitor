from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Backup, DatabaseSizeSnapshot, Schedule
from app.services import audit_service, mysql_service, storage_service
from app.utils import now


def compute_next_run(frequency: str, run_time: str, day_of_week: Optional[int] = None, base: Optional[datetime] = None) -> datetime:
    base = base or now()
    try:
        hour, minute = (int(part) for part in run_time.split(":", 1))
    except ValueError:
        hour, minute = 2, 0
    hour = min(max(hour, 0), 23)
    minute = min(max(minute, 0), 59)

    if frequency == "weekly":
        weekday = day_of_week if day_of_week is not None else 0
        weekday = int(weekday) % 7
        candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (weekday - candidate.weekday()) % 7
        candidate = candidate + timedelta(days=days_ahead)
        if candidate <= base:
            candidate = candidate + timedelta(days=7)
        return candidate

    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= base:
        candidate = candidate + timedelta(days=1)
    return candidate


def due_schedules(db: Session) -> list[Schedule]:
    now = now()
    return (
        db.query(Schedule)
        .filter(Schedule.enabled.is_(True))
        .filter(Schedule.next_run_at.isnot(None))
        .filter(Schedule.next_run_at <= now)
        .order_by(Schedule.next_run_at.asc())
        .all()
    )


def process_due_schedules(db: Session) -> list[int]:
    from app.services import backup_service

    created_jobs: list[int] = []
    for schedule in due_schedules(db):
        try:
            job = backup_service.create_backup_job(db, schedule.database_name, actor="scheduler")
            created_jobs.append(job.id)
            schedule.last_run_at = now()
        except ValueError:
            schedule.next_run_at = now() + timedelta(days=1)
            audit_service.log_event(
                db,
                actor="scheduler",
                action="scheduled_backup_skipped",
                status="failed",
                database_name=schedule.database_name,
                detail="Database no longer available; rescheduled for tomorrow",
            )
        else:
            schedule.next_run_at = compute_next_run(schedule.frequency, schedule.run_time, schedule.day_of_week)
    if created_jobs:
        db.commit()
    return created_jobs


def capture_size_snapshots(db: Session, min_interval_minutes: int = 60) -> int:
    overview = mysql_service.get_database_overview(show_system=False)
    now = now()
    inserted = 0
    for item in overview:
        latest = (
            db.query(DatabaseSizeSnapshot)
            .filter(DatabaseSizeSnapshot.database_name == item["name"])
            .order_by(DatabaseSizeSnapshot.captured_at.desc())
            .first()
        )
        if latest is not None:
            age = now - latest.captured_at
            if age < timedelta(minutes=min_interval_minutes):
                continue
        db.add(
            DatabaseSizeSnapshot(
                database_name=item["name"],
                total_bytes=int(item["total_size"]),
                table_count=int(item["table_count"]),
                captured_at=now,
            )
        )
        inserted += 1
    if inserted:
        db.commit()
    return inserted


def run_retention(db: Session) -> dict:
    retention_days = storage_service.get_int_setting(db, "retention_days", settings.BACKUP_RETENTION_DAYS)
    if retention_days <= 0:
        return {"deleted": 0, "freed_bytes": 0}
    cutoff = now() - timedelta(days=retention_days)
    old_backups = (
        db.query(Backup)
        .filter(Backup.created_at < cutoff)
        .filter(Backup.status == "success")
        .filter(Backup.is_ephemeral.is_(False))
        .all()
    )
    deleted = 0
    freed = 0
    for backup in old_backups:
        candidate = storage_service.safe_backup_path(backup.relative_path or backup.filename)
        if candidate is not None and candidate.exists():
            try:
                freed += candidate.stat().st_size
                candidate.unlink()
            except OSError as exc:
                audit_service.log_event(
                    db,
                    actor="retention",
                    action="retention_delete_failed",
                    status="failed",
                    filename=backup.filename,
                    detail=str(exc),
                )
                continue
        db.delete(backup)
        deleted += 1
        audit_service.log_event(
            db,
            actor="retention",
            action="retention_cleanup",
            status="success",
            database_name=backup.database_name,
            filename=backup.filename,
            detail=f"Deleted backup older than {retention_days} days",
        )
    db.commit()
    return {"deleted": deleted, "freed_bytes": freed, "retention_days": retention_days}
