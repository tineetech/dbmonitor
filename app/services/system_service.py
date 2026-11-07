import os
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import HostResourceSnapshot
from app.utils import now

try:
    import psutil
except ImportError:
    psutil = None


def _load_average() -> tuple[Optional[float], Optional[float], Optional[float]]:
    try:
        values = os.getloadavg()
    except (AttributeError, OSError):
        return None, None, None
    return float(values[0]), float(values[1]), float(values[2])


def host_resources() -> dict:
    if psutil is None:
        return {
            "ram": {"total": 0, "used": 0, "available": 0, "percent": 0.0},
            "cpu": {"percent": 0.0, "count": 0, "load_avg_1m": None, "load_avg_5m": None, "load_avg_15m": None},
        }
    memory = psutil.virtual_memory()
    load_1m, load_5m, load_15m = _load_average()
    return {
        "ram": {
            "total": int(memory.total),
            "used": int(memory.used),
            "available": int(memory.available),
            "percent": float(memory.percent),
        },
        "cpu": {
            "percent": float(psutil.cpu_percent(interval=0.1)),
            "count": int(psutil.cpu_count(logical=True) or 0),
            "load_avg_1m": load_1m,
            "load_avg_5m": load_5m,
            "load_avg_15m": load_15m,
        },
    }


def capture_host_snapshot(db: Session, min_interval_minutes: int = 60) -> bool:
    current_time = now()
    latest = db.query(HostResourceSnapshot).order_by(HostResourceSnapshot.captured_at.desc()).first()
    if latest is not None and current_time - latest.captured_at < timedelta(minutes=min_interval_minutes):
        return False
    resources = host_resources()
    ram = resources["ram"]
    cpu = resources["cpu"]
    db.add(
        HostResourceSnapshot(
            captured_at=current_time,
            ram_total_bytes=int(ram["total"]),
            ram_used_bytes=int(ram["used"]),
            ram_percent=float(ram["percent"]),
            cpu_percent=float(cpu["percent"]),
            cpu_count=int(cpu["count"]),
            load_avg_1m=cpu["load_avg_1m"],
            load_avg_5m=cpu["load_avg_5m"],
            load_avg_15m=cpu["load_avg_15m"],
        )
    )
    db.commit()
    return True


def prune_host_snapshots(db: Session, retention_days: int = 90) -> int:
    cutoff = now() - timedelta(days=max(1, retention_days))
    removed = (
        db.query(HostResourceSnapshot)
        .filter(HostResourceSnapshot.captured_at < cutoff)
        .delete(synchronize_session=False)
    )
    if removed:
        db.commit()
    return int(removed)
