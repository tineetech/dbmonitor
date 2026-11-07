from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import client_ip, get_current_full_access, require_csrf
from app.models import Schedule
from app.schemas.schemas import ScheduleCreateRequest, ScheduleUpdateRequest
from app.services import audit_service, mysql_service, scheduler_service

router = APIRouter(prefix="/api/v1/schedules", tags=["schedules"])


def _serialize(schedule: Schedule) -> dict:
    return {
        "id": schedule.id,
        "database_name": schedule.database_name,
        "frequency": schedule.frequency,
        "run_time": schedule.run_time,
        "day_of_week": schedule.day_of_week,
        "enabled": bool(schedule.enabled),
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "created_by": schedule.created_by,
        "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
    }


@router.get("")
def list_schedules(db: Session = Depends(get_db), user: dict = Depends(get_current_full_access)):
    del user
    schedules = db.query(Schedule).order_by(Schedule.created_at.desc()).all()
    return {"schedules": [_serialize(item) for item in schedules]}


@router.post("")
def create_schedule(
    payload: ScheduleCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
    _csrf: dict = Depends(require_csrf),
):
    if not mysql_service.is_known_database(payload.database_name, show_system=settings.SHOW_SYSTEM_DATABASES):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown or inaccessible database")
    schedule = Schedule(
        database_name=payload.database_name,
        frequency=payload.frequency,
        run_time=payload.run_time,
        day_of_week=payload.day_of_week if payload.frequency == "weekly" else None,
        enabled=payload.enabled,
        next_run_at=scheduler_service.compute_next_run(payload.frequency, payload.run_time, payload.day_of_week),
        created_by=user["username"],
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    audit_service.log_event(
        db,
        actor=user["username"],
        action="schedule_created",
        status="success",
        database_name=payload.database_name,
        ip_address=client_ip(request),
        detail=f"Schedule #{schedule.id} ({payload.frequency} at {payload.run_time})",
    )
    return JSONResponse(_serialize(schedule), status_code=status.HTTP_201_CREATED)


@router.put("/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
    _csrf: dict = Depends(require_csrf),
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    if payload.frequency is not None:
        schedule.frequency = payload.frequency
    if payload.run_time is not None:
        schedule.run_time = payload.run_time
    if payload.frequency is not None or payload.day_of_week is not None:
        schedule.day_of_week = payload.day_of_week if schedule.frequency == "weekly" else None
    if payload.enabled is not None:
        schedule.enabled = payload.enabled
    schedule.next_run_at = scheduler_service.compute_next_run(schedule.frequency, schedule.run_time, schedule.day_of_week)
    db.commit()
    db.refresh(schedule)
    audit_service.log_event(
        db,
        actor=user["username"],
        action="schedule_updated",
        status="success",
        database_name=schedule.database_name,
        ip_address=client_ip(request),
        detail=f"Schedule #{schedule.id}",
    )
    return _serialize(schedule)


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_full_access),
    _csrf: dict = Depends(require_csrf),
):
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    database_name = schedule.database_name
    db.delete(schedule)
    db.commit()
    audit_service.log_event(
        db,
        actor=user["username"],
        action="schedule_deleted",
        status="success",
        database_name=database_name,
        ip_address=client_ip(request),
        detail=f"Schedule #{schedule_id} removed",
    )
    return {"detail": "Schedule deleted"}

