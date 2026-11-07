import argparse
import signal
import sys
import time
import traceback
from datetime import timedelta

from app.database import SessionLocal, init_db
from app.services import backup_service, scheduler_service, system_service
from app.utils import now

STOP_REQUESTED = False
LAST_RETENTION_RUN = None
RETENTION_INTERVAL = timedelta(hours=24)


def handle_signal(signum, frame):  # noqa: ARG001
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main() -> int:
    parser = argparse.ArgumentParser(description="DB Monitor scheduler worker")
    parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    init_db()
    print("[scheduler] Scheduler worker started")

    global LAST_RETENTION_RUN
    LAST_RETENTION_RUN = now() - RETENTION_INTERVAL

    while not STOP_REQUESTED:
        db = SessionLocal()
        try:
            created = scheduler_service.process_due_schedules(db)
            snapshots = scheduler_service.capture_size_snapshots(db, min_interval_minutes=60)
            host_captured = system_service.capture_host_snapshot(db, min_interval_minutes=60)
            ephemeral_removed = backup_service.cleanup_expired_ephemeral(db)
            if created:
                print(f"[scheduler] Enqueued {len(created)} scheduled backup job(s)")
            if snapshots:
                print(f"[scheduler] Captured {snapshots} size snapshot(s)")
            if host_captured:
                print("[scheduler] Captured host resource snapshot")
            if ephemeral_removed:
                print(f"[scheduler] Removed {ephemeral_removed} expired ephemeral quick backup(s)")

            if now() - LAST_RETENTION_RUN >= RETENTION_INTERVAL:
                result = scheduler_service.run_retention(db)
                pruned = system_service.prune_host_snapshots(db)
                LAST_RETENTION_RUN = now()
                if result["deleted"]:
                    print(f"[scheduler] Retention removed {result['deleted']} old backup(s), freed {result['freed_bytes']} bytes")
                if pruned:
                    print(f"[scheduler] Pruned {pruned} old host snapshot(s)")
        except Exception:
            traceback.print_exc()
        finally:
            db.close()
        time.sleep(30)

    print("[scheduler] Shutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
