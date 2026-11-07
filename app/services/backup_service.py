import hashlib
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Backup, BackupJob
from app.services import audit_service, mysql_service, storage_service
from app.utils import now

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def sanitize_filename_stem(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name.strip())[:64].strip("_")
    return cleaned or "database"


def list_backupable_databases() -> list[str]:
    names = mysql_service.list_database_names(show_system=settings.SHOW_SYSTEM_DATABASES)
    return names


def create_backup_job(
    db: Session,
    database_name: str,
    actor: str,
    ip_address: Optional[str] = None,
    ephemeral: bool = False,
) -> BackupJob:
    valid = mysql_service.is_known_database(database_name, show_system=settings.SHOW_SYSTEM_DATABASES)
    if not valid:
        raise ValueError("Unknown or inaccessible database")
    job = BackupJob(
        database_name=database_name,
        status="pending",
        requested_by=actor,
        is_ephemeral=bool(ephemeral),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    audit_service.log_event(
        db,
        actor=actor,
        action="backup_requested",
        status="success",
        database_name=database_name,
        ip_address=ip_address,
        detail=f"Backup job #{job.id} created" + (" (ephemeral quick backup)" if ephemeral else ""),
    )
    return job


def claim_pending_jobs(db: Session, limit: int, worker_id: str) -> list[int]:
    claimed: list[int] = []
    for _ in range(limit):
        candidate = db.execute(
            text("SELECT id FROM backup_jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1")
        ).scalar()
        if candidate is None:
            break
        result = db.execute(
            text(
                """
                UPDATE backup_jobs
                SET status = 'processing', started_at = :started_at, worker_id = :worker_id
                WHERE id = :job_id AND status = 'pending'
                """
            ),
            {"worker_id": worker_id, "job_id": candidate, "started_at": now()},
        )
        db.commit()
        if result.rowcount == 1:
            claimed.append(int(candidate))
    return claimed


def _temp_defaults_file(directory: Path) -> Path:
    defaults = directory / "client.cnf"
    lines = [
        "[client]",
        f"host={settings.DB_HOST}",
        f"port={settings.DB_PORT}",
        f"user={settings.DB_USERNAME}",
        f"password={settings.DB_PASSWORD}",
    ]
    defaults.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(defaults, 0o600)
    except OSError:
        pass
    return defaults


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fail_job(db: Session, job_id: int, database_name: str, error: str, delete_file: Optional[Path]) -> None:
    job = db.get(BackupJob, job_id)
    if job:
        job.status = "failed"
        job.error = error[:2000]
        job.finished_at = now()
        db.commit()
    if delete_file is not None:
        try:
            delete_file.unlink(missing_ok=True)
        except OSError:
            pass
    audit_service.log_event(
        db,
        actor="backup_worker",
        action="backup_failed",
        status="failed",
        database_name=database_name,
        detail=error[:2000],
    )


def run_backup_job(db: Session, job_id: int) -> None:
    job = db.get(BackupJob, job_id)
    if not job:
        return
    database_name = job.database_name

    if not mysql_service.is_known_database(database_name, show_system=settings.SHOW_SYSTEM_DATABASES):
        _fail_job(db, job_id, database_name, "Database no longer exists or is not accessible", None)
        return

    free_bytes = shutil.disk_usage(str(settings.backup_dir)).free
    if free_bytes < 64 * 1024 * 1024:
        _fail_job(db, job_id, database_name, "Insufficient disk space (< 64 MB free)", None)
        return

    stamp = now().strftime("%Y%m%d_%H%M%S")
    filename = f"{sanitize_filename_stem(database_name)}_{stamp}_{secrets.token_hex(3)}.sql"
    output_path = settings.backup_dir / filename

    tmp_dir = Path(tempfile.mkdtemp(prefix="dbmonitor_"))
    try:
        defaults = _temp_defaults_file(tmp_dir)
        dump_binary = settings.resolve_dump_binary()
        args = [
            dump_binary,
            f"--defaults-extra-file={defaults}",
            "--single-transaction",
            "--quick",
            "--routines",
            "--triggers",
            "--events",
            "--hex-blob",
            "--default-character-set=utf8mb4",
            f"--result-file={output_path}",
            database_name,
        ]
        try:
            completed = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                timeout=settings.BACKUP_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _fail_job(db, job_id, database_name, f"Backup timed out after {settings.BACKUP_TIMEOUT_SECONDS} seconds", output_path)
            return
        except OSError as exc:
            _fail_job(db, job_id, database_name, f"Failed to execute dump binary: {exc}", output_path)
            return

        stderr = (completed.stderr or b"").decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else str(completed.stderr or "")

        if completed.returncode != 0:
            detail = stderr.strip() or f"Dump exited with code {completed.returncode}"
            _fail_job(db, job_id, database_name, detail, output_path)
            return

        if not output_path.exists() or output_path.stat().st_size == 0:
            _fail_job(db, job_id, database_name, "Dump produced an empty or missing file", output_path)
            return

        file_size = output_path.stat().st_size
        checksum = _sha256_file(output_path)

        backup = Backup(
            filename=filename,
            database_name=database_name,
            relative_path=filename,
            file_size=file_size,
            sha256=checksum,
            status="success",
            is_ephemeral=bool(job.is_ephemeral),
        )
        db.add(backup)
        db.flush()

        job = db.get(BackupJob, job_id)
        job.status = "success"
        job.finished_at = now()
        job.file_id = backup.id
        db.commit()

        audit_service.log_event(
            db,
            actor="backup_worker",
            action="backup_success",
            status="success",
            database_name=database_name,
            filename=filename,
            detail=f"size={file_size} sha256={checksum}" + (" ephemeral=yes" if backup.is_ephemeral else ""),
        )
    except Exception as exc:  # noqa: BLE001
        _fail_job(db, job_id, database_name, f"Unexpected error: {exc}", output_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def fail_stale_processing_jobs(db: Session, reason: str = "Worker restarted before job completion") -> int:
    stale = db.query(BackupJob).filter(BackupJob.status == "processing").all()
    count = 0
    for job in stale:
        job.status = "failed"
        job.error = reason
        job.finished_at = now()
        count += 1
    if count:
        db.commit()
        audit_service.log_event(
            db,
            actor="backup_worker",
            action="jobs_marked_failed",
            status="failed",
            detail=f"Marked {count} stale processing job(s) as failed",
        )
    return count


def delete_backup_entry(db: Session, backup_id: int, actor: str = "system", reason: str = "") -> bool:
    """Delete a backup file (if present) and its metadata row. Used for ephemeral quick backups."""
    backup = db.get(Backup, backup_id)
    if backup is None:
        return False
    filename = backup.filename
    database_name = backup.database_name
    is_ephemeral = bool(backup.is_ephemeral)

    candidate = storage_service.safe_backup_path(backup.relative_path or backup.filename)
    if candidate is not None and candidate.exists():
        try:
            candidate.unlink()
        except OSError:
            return False

    db.query(BackupJob).filter(BackupJob.file_id == backup.id).update(
        {BackupJob.file_id: None}, synchronize_session=False
    )
    db.delete(backup)
    db.commit()

    audit_service.log_event(
        db,
        actor=actor,
        action="ephemeral_backup_deleted" if is_ephemeral else "backup_deleted",
        status="success",
        database_name=database_name,
        filename=filename,
        detail=reason[:2000] or "Backup file removed from server",
    )
    return True


def cleanup_expired_ephemeral(db: Session, max_age_minutes: Optional[int] = None) -> int:
    """Remove ephemeral backups that were never downloaded within the TTL window."""
    age = settings.EPHEMERAL_TTL_MINUTES if max_age_minutes is None else int(max_age_minutes)
    cutoff = now() - timedelta(minutes=max(1, age))
    rows = (
        db.query(Backup)
        .filter(Backup.is_ephemeral.is_(True))
        .filter(Backup.created_at < cutoff)
        .all()
    )
    removed = 0
    for row in rows:
        if delete_backup_entry(
            db,
            row.id,
            actor="ephemeral_cleanup",
            reason=f"Ephemeral quick backup older than {age} minutes and never downloaded",
        ):
            removed += 1
    return removed
