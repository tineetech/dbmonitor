from datetime import datetime, timedelta, timezone

from app.config import settings

APP_TIMEZONE = timezone(timedelta(hours=settings.APP_TIMEZONE_OFFSET_HOURS))


def now() -> datetime:
    """Naive app-local timestamp (default WIB / UTC+7) for DATETIME columns."""
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def tz_offset_string() -> str:
    total_minutes = int(settings.APP_TIMEZONE_OFFSET_HOURS * 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def utcnow() -> datetime:
    """Deprecated alias kept for compatibility; returns app-local (WIB) now."""
    return now()
