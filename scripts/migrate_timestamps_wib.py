import argparse
import sys

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.models import AppSetting, Schedule
from app.services import scheduler_service
from app.utils import now

MARKER = "tz_migration_utc_to_wib"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shift app DATETIME columns from UTC to WIB (one-time migration)."
    )
    parser.add_argument("--apply", action="store_true", help="Execute the migration")
    parser.add_argument(
        "--offset-hours",
        type=int,
        default=settings.APP_TIMEZONE_OFFSET_HOURS,
        help="Hours to add (default: APP_TIMEZONE_OFFSET_HOURS)",
    )
    parser.add_argument("--force", action="store_true", help="Run even if the marker exists")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        marker = db.get(AppSetting, MARKER)
        if marker and not args.force:
            print(f"Migration already applied at {marker.value}. Use --force to run again.")
            return 0

        columns = db.execute(
            text(
                "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = :schema AND DATA_TYPE = 'datetime' "
                "ORDER BY TABLE_NAME, ORDINAL_POSITION"
            ),
            {"schema": settings.DB_NAME},
        ).all()
        if not columns:
            print("No DATETIME columns found.")
            return 1

        planned = []
        total = 0
        for table, column in columns:
            count = int(
                db.execute(text(f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` IS NOT NULL")).scalar() or 0
            )
            planned.append((table, column))
            total += count
            print(f"{table}.{column}: {count} row(s)")
        print(f"Total {total} value(s) across {len(columns)} column(s); offset +{args.offset_hours}h")

        if not args.apply:
            print("Dry run only. Re-run with --apply to execute.")
            return 0

        hours = int(args.offset_hours)
        for table, column in planned:
            db.execute(
                text(
                    f"UPDATE `{table}` SET `{column}` = DATE_ADD(`{column}`, INTERVAL {hours} HOUR) "
                    f"WHERE `{column}` IS NOT NULL"
                )
            )

        schedules = db.query(Schedule).filter(Schedule.enabled.is_(True)).all()
        for schedule in schedules:
            schedule.next_run_at = scheduler_service.compute_next_run(
                schedule.frequency, schedule.run_time, schedule.day_of_week
            )

        stamp = now().isoformat(sep=" ")
        if marker:
            marker.value = stamp
        else:
            db.add(AppSetting(key=MARKER, value=stamp))
        db.commit()
        print(
            f"Applied +{hours}h to {total} value(s); recomputed next_run for {len(schedules)} schedule(s)."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
