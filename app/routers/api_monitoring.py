from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_full_access, get_current_user, require_csrf
from app.models import DatabaseSizeSnapshot
from app.services import mysql_service, scheduler_service, storage_service

router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])


@router.get("/health")
def health(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    del db, user
    server = mysql_service.get_server_status()
    if not server["connected"]:
        return {"mysql": server, "status": "disconnected"}
    return {"mysql": server, "status": "connected"}


@router.get("/storage")
def storage(db: Session = Depends(get_db), user: dict = Depends(get_current_full_access)):
    del user
    return storage_service.storage_status(db)


@router.get("/growth")
def growth(
    database_name: Optional[str] = Query(default=None, max_length=64),
    limit: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
):
    del user
    query = db.query(DatabaseSizeSnapshot).order_by(DatabaseSizeSnapshot.captured_at.asc())
    if database_name:
        query = query.filter(DatabaseSizeSnapshot.database_name == database_name)
    rows = query.all()

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.database_name, []).append(
            {
                "captured_at": row.captured_at.isoformat() if row.captured_at else None,
                "total_bytes": int(row.total_bytes),
                "table_count": int(row.table_count),
            }
        )

    series = []
    for name, points in grouped.items():
        points = points[-limit:]
        latest = points[-1] if points else None
        previous = points[-2] if len(points) >= 2 else None
        delta = (latest["total_bytes"] - previous["total_bytes"]) if latest and previous else None
        series.append({"database_name": name, "points": points, "latest_bytes": latest["total_bytes"] if latest else 0, "delta_bytes": delta})

    series.sort(key=lambda item: item["latest_bytes"], reverse=True)
    return {"series": series}


@router.post("/snapshot")
def capture_snapshot(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
    _csrf: dict = Depends(require_csrf),
):
    del _csrf
    inserted = scheduler_service.capture_size_snapshots(db, min_interval_minutes=0)
    return {"inserted": inserted, "actor": user["username"]}

