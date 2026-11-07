from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_full_access
from app.models import AuditLog

router = APIRouter(prefix="/api/v1/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    search: Optional[str] = Query(default=None, max_length=128),
    action: Optional[str] = Query(default=None, max_length=64),
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=20),
    sort: str = Query(default="created_at", max_length=20),
    order: str = Query(default="desc", max_length=4),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=15, ge=1, le=100),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
):
    del user
    query = db.query(AuditLog)
    if search:
        needle = f"%{search.strip()}%"
        query = query.filter(
            (AuditLog.actor.like(needle))
            | (AuditLog.database_name.like(needle))
            | (AuditLog.filename.like(needle))
            | (AuditLog.detail.like(needle))
        )
    if action:
        query = query.filter(AuditLog.action == action)
    if status_filter:
        query = query.filter(AuditLog.status == status_filter)

    sort_column = AuditLog.created_at if sort != "actor" else AuditLog.actor
    order_fn = asc if order == "asc" else desc

    total = query.count()
    rows = (
        query.order_by(order_fn(sort_column))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "logs": [
            {
                "id": row.id,
                "actor": row.actor,
                "action": row.action,
                "database_name": row.database_name,
                "filename": row.filename,
                "ip_address": row.ip_address,
                "status": row.status,
                "detail": row.detail,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }

