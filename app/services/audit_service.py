from typing import Optional

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_event(
    db: Session,
    actor: str,
    action: str,
    status: str = "success",
    database_name: Optional[str] = None,
    filename: Optional[str] = None,
    ip_address: Optional[str] = None,
    detail: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor[:64],
        action=action[:64],
        database_name=database_name[:64] if database_name else None,
        filename=filename[:255] if filename else None,
        ip_address=ip_address[:45] if ip_address else None,
        status=status[:20],
        detail=(detail or "")[:2000] if detail else None,
    )
    db.add(entry)
    db.commit()
    return entry
