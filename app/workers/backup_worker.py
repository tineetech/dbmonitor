import argparse
import signal
import sys
import time
import traceback

from app.config import settings
from app.database import SessionLocal, init_db
from app.services import backup_service, storage_service

STOP_REQUESTED = False


def handle_signal(signum, frame):  # noqa: ARG001
    global STOP_REQUESTED
    STOP_REQUESTED = True


def process_queue(worker_id: str) -> int:
    db = SessionLocal()
    try:
        limit = storage_service.get_int_setting(
            db, "max_concurrent_backups", settings.MAX_CONCURRENT_BACKUPS
        )
        limit = max(1, min(int(limit), 10))
        job_ids = backup_service.claim_pending_jobs(db, limit, worker_id)
        if not job_ids:
            return 0
        for job_id in job_ids:
            backup_service.run_backup_job(db, job_id)
        return len(job_ids)
    except Exception:
        traceback.print_exc()
        return -1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="DB Monitor backup worker")
    parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    init_db()
    worker_id = f"worker-{os_hostname()}-{int(time.time()) % 100000}"

    startup_db = SessionLocal()
    try:
        restored = backup_service.fail_stale_processing_jobs(startup_db)
        if restored:
            print(f"[worker] Marked {restored} stale processing job(s) as failed")
    finally:
        startup_db.close()

    print(f"[worker] Backup worker started (id={worker_id}, concurrency={settings.MAX_CONCURRENT_BACKUPS})")
    idle_sleep = 2.0
    while not STOP_REQUESTED:
        processed = process_queue(worker_id)
        if processed > 0:
            print(f"[worker] Processed {processed} backup job(s)")
            time.sleep(0.5)
        else:
            time.sleep(idle_sleep)
    print("[worker] Shutting down")
    return 0


def os_hostname() -> str:
    import socket

    try:
        return socket.gethostname().split(".")[0][:24]
    except OSError:
        return "local"


if __name__ == "__main__":
    sys.exit(main())
