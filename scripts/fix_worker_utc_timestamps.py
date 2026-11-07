import argparse
import sys
from datetime import timedelta

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog, Backup, BackupJob


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fix rows written by stale workers that still used UTC after the WIB migration."
    )
    parser.add_argument("--apply", action="store_true", help="Execute the correction")
    args = parser.parse_args()

    offset = timedelta(hours=settings.APP_TIMEZONE_OFFSET_HOURS)
    db = SessionLocal()
    try:
        job_fixes = []
        for job in db.query(BackupJob).filter(BackupJob.started_at.isnot(None)).all():
            if job.created_at and job.started_at and job.started_at < job.created_at - timedelta(hours=1):
                job_fixes.append(job)

        backup_fixes = []
        for backup in db.query(Backup).all():
            job = backup.job
            if job and job.created_at and backup.created_at < job.created_at - timedelta(hours=1):
                backup_fixes.append(backup)

        audit_fixes = []
        for job in job_fixes:
            low = job.started_at - timedelta(minutes=5)
            high = (job.finished_at or job.started_at) + timedelta(minutes=5)
            rows = (
                db.query(AuditLog)
                .filter(AuditLog.actor == "backup_worker")
                .filter(AuditLog.database_name == job.database_name)
                .filter(AuditLog.created_at >= low)
                .filter(AuditLog.created_at <= high)
                .all()
            )
            for row in rows:
                if row not in audit_fixes:
                    audit_fixes.append(row)

        print(f"Jobs to shift (+{settings.APP_TIMEZONE_OFFSET_HOURS}h): {len(job_fixes)}")
        for job in job_fixes:
            print(f"  job #{job.id} {job.database_name}: created={job.created_at} started={job.started_at} finished={job.finished_at}")
        print(f"Backups to shift: {len(backup_fixes)}")
        for backup in backup_fixes:
            print(f"  backup #{backup.id} {backup.filename}: {backup.created_at}")
        print(f"Worker audit logs to shift: {len(audit_fixes)}")
        for row in audit_fixes:
            print(f"  audit #{row.id} {row.action} {row.database_name}: {row.created_at}")

        if not args.apply:
            print("Dry run only. Re-run with --apply to execute.")
            return 0

        for job in job_fixes:
            if job.started_at:
                job.started_at = job.started_at + offset
            if job.finished_at:
                job.finished_at = job.finished_at + offset
        for backup in backup_fixes:
            backup.created_at = backup.created_at + offset
        for row in audit_fixes:
            row.created_at = row.created_at + offset

        db.commit()
        print(
            f"Applied +{settings.APP_TIMEZONE_OFFSET_HOURS}h to {len(job_fixes)} job(s), "
            f"{len(backup_fixes)} backup(s), {len(audit_fixes)} audit log(s)."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
