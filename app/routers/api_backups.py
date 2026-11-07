from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import (
    FULL_ACCESS_ROLES,
    client_ip,
    get_current_full_access,
    get_current_user,
    require_csrf,
)
from app.models import Backup, BackupJob
from app.schemas.schemas import BackupCreateRequest
from app.services import audit_service, backup_service, storage_service

router = APIRouter(prefix="/api/v1/backups", tags=["backups"])

DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def _stream_ephemeral(backup_id: int, path: Path, filename: str, checksum: str) -> StreamingResponse:
    """Stream an ephemeral backup and delete it from the server once sending finishes."""

    def iterator():
        try:
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
        finally:
            cleanup_db = SessionLocal()
            try:
                backup_service.delete_backup_entry(
                    cleanup_db,
                    backup_id,
                    actor="system",
                    reason="Ephemeral quick backup deleted immediately after download",
                )
            finally:
                cleanup_db.close()

    return StreamingResponse(
        iterator(),
        media_type="application/sql",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(path.stat().st_size),
            "X-Checksum-SHA256": checksum or "",
        },
    )


@router.post("")
def create_backup(
    payload: BackupCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
    _csrf: dict = Depends(require_csrf),
):
    if user["role"] not in FULL_ACCESS_ROLES and not payload.ephemeral:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account may only create ephemeral quick downloads",
        )
    try:
        job = backup_service.create_backup_job(
            db,
            payload.database_name,
            actor=user["username"],
            ip_address=client_ip(request),
            ephemeral=payload.ephemeral,
        )
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown or inaccessible database")
    poll_url = f"/api/v1/backups/jobs/{job.id}"
    return JSONResponse(
        {
            "backup_id": job.id,
            "job_id": job.id,
            "status": job.status,
            "database_name": job.database_name,
            "ephemeral": bool(job.is_ephemeral),
            "poll_url": poll_url,
        },
        status_code=status.HTTP_202_ACCEPTED,
    )


@router.get("/jobs")
def list_jobs(
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
):
    del user
    query = db.query(BackupJob)
    if status_filter:
        query = query.filter(BackupJob.status == status_filter)
    jobs = query.order_by(BackupJob.created_at.desc()).limit(limit).all()
    return {
        "jobs": [
            {
                "id": job.id,
                "database_name": job.database_name,
                "status": job.status,
                "requested_by": job.requested_by,
                "error": job.error,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }
            for job in jobs
        ]
    }


@router.get("/jobs/{job_id}")
def job_status(job_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    job = db.get(BackupJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if user["role"] not in FULL_ACCESS_ROLES and (
        not job.is_ephemeral or job.requested_by != user["username"]
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    payload = {
        "id": job.id,
        "job_id": job.id,
        "backup_id": job.id,
        "database_name": job.database_name,
        "status": job.status,
        "is_ephemeral": bool(job.is_ephemeral),
        "requested_by": job.requested_by,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "filename": None,
        "file_size": None,
        "checksum": None,
        "download_url": None,
    }
    if job.file_id:
        backup = db.get(Backup, job.file_id)
        if backup:
            candidate = storage_service.safe_backup_path(backup.relative_path or backup.filename)
            exists = candidate.exists() if candidate else False
            payload.update(
                {
                    "filename": backup.filename,
                    "file_size": int(backup.file_size),
                    "checksum": backup.sha256,
                    "file_status": backup.status,
                    "file_exists": exists,
                    "download_url": f"/api/v1/backups/{backup.id}/download" if exists else None,
                }
            )
    return payload


@router.get("")
def list_backups(
    search: Optional[str] = Query(default=None, max_length=128),
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=20),
    database_name: Optional[str] = Query(default=None, max_length=64),
    date_from: Optional[str] = Query(default=None, max_length=10),
    date_to: Optional[str] = Query(default=None, max_length=10),
    sort: str = Query(default="created_at", max_length=20),
    order: str = Query(default="desc", max_length=4),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    del user
    query = db.query(Backup).filter(Backup.is_ephemeral.is_(False))
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter((Backup.filename.like(needle)) | (Backup.database_name.like(needle)))
    if status_filter:
        query = query.filter(Backup.status == status_filter)
    if database_name:
        query = query.filter(Backup.database_name == database_name)

    def parse_date(value: str) -> Optional[datetime]:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    start = parse_date(date_from) if date_from else None
    end = parse_date(date_to) if date_to else None
    if start:
        query = query.filter(Backup.created_at >= start)
    if end:
        query = query.filter(Backup.created_at < end.replace(hour=23, minute=59, second=59))

    sort_column = {
        "created_at": Backup.created_at,
        "filename": Backup.filename,
        "file_size": Backup.file_size,
        "database_name": Backup.database_name,
    }.get(sort, Backup.created_at)
    order_fn = asc if order == "asc" else desc

    total = query.count()
    rows = (
        query.order_by(order_fn(sort_column))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = max(1, (total + per_page - 1) // per_page)

    items = []
    for row in rows:
        candidate = storage_service.safe_backup_path(row.relative_path or row.filename)
        items.append(
            {
                "id": row.id,
                "filename": row.filename,
                "database_name": row.database_name,
                "file_size": int(row.file_size),
                "sha256": row.sha256,
                "status": row.status,
                "file_exists": bool(candidate and candidate.exists()),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "backups": items,
    }


@router.get("/{backup_id}")
def backup_detail(backup_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    backup = db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    if backup.is_ephemeral and user["role"] not in FULL_ACCESS_ROLES:
        owned = (
            db.query(BackupJob)
            .filter(BackupJob.file_id == backup.id)
            .filter(BackupJob.requested_by == user["username"])
            .first()
        )
        if owned is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    candidate = storage_service.safe_backup_path(backup.relative_path or backup.filename)
    exists = bool(candidate and candidate.exists())
    related_job = (
        db.query(BackupJob)
        .filter(BackupJob.file_id == backup.id)
        .order_by(BackupJob.created_at.desc())
        .first()
    )
    return {
        "id": backup.id,
        "filename": backup.filename,
        "database_name": backup.database_name,
        "file_size": int(backup.file_size),
        "sha256": backup.sha256,
        "status": backup.status,
        "file_exists": exists,
        "created_at": backup.created_at.isoformat() if backup.created_at else None,
        "requested_by": related_job.requested_by if related_job else None,
        "download_url": f"/api/v1/backups/{backup.id}/download" if exists else None,
    }


@router.get("/{backup_id}/download")
def download_backup(
    backup_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    backup = db.get(Backup, backup_id)
    if not backup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    if user["role"] not in FULL_ACCESS_ROLES:
        if backup.is_ephemeral:
            owned = (
                db.query(BackupJob)
                .filter(BackupJob.file_id == backup.id)
                .filter(BackupJob.requested_by == user["username"])
                .first()
            )
            if owned is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges")
    candidate = storage_service.safe_backup_path(backup.relative_path or backup.filename)
    if candidate is None or not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file is missing")
    audit_service.log_event(
        db,
        actor=user["username"],
        action="backup_downloaded",
        status="success",
        database_name=backup.database_name,
        filename=backup.filename,
        ip_address=client_ip(request),
        detail="ephemeral quick backup (single download)" if backup.is_ephemeral else None,
    )
    if backup.is_ephemeral:
        return _stream_ephemeral(
            backup.id,
            candidate,
            backup.filename,
            backup.sha256,
        )
    return FileResponse(
        path=str(candidate),
        filename=backup.filename,
        media_type="application/sql",
        headers={"X-Checksum-SHA256": backup.sha256 or ""},
    )
