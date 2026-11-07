import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import Backup
from app.services import audit_service, storage_service

TEST_DATABASE = "db_monitor_restore_test"


def find_mysql_client() -> Path:
    dump_path = Path(settings.MYSQL_DUMP_PATH)
    names = ["mysql.exe", "mysql", "mariadb.exe", "mariadb"]
    if dump_path.parent.exists():
        for name in names:
            candidate = dump_path.parent / name
            if candidate.exists():
                return candidate
    for name in ("mysql", "mariadb"):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise FileNotFoundError("mysql client binary not found. Set MYSQL_DUMP_PATH or add mysql to PATH.")


def write_defaults(directory: Path) -> Path:
    # Optional override for restore testing: the dump may contain DEFINER clauses
    # that require elevated privileges. Defaults to the application account.
    user = os.getenv("RESTORE_TEST_DB_USERNAME") or settings.DB_USERNAME
    password_env = os.getenv("RESTORE_TEST_DB_PASSWORD")
    if password_env == "-":
        password = ""
    elif password_env is not None:
        password = password_env
    else:
        password = settings.DB_PASSWORD
    defaults = directory / "client.cnf"
    lines = [
        "[client]",
        f"host={settings.DB_HOST}",
        f"port={settings.DB_PORT}",
        f"user={user}",
    ]
    if password:
        lines.append(f"password={password}")
    defaults.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return defaults


def run_mysql(client: Path, defaults: Path, database: str | None, args: list[str], stdin_path: Path | None = None) -> None:
    command = [str(client), f"--defaults-extra-file={defaults}"]
    if database:
        command.append(database)
    command += args
    if stdin_path is not None:
        with stdin_path.open("rb") as handle:
            subprocess.run(command, shell=False, check=True, stdin=handle, capture_output=True)
    else:
        subprocess.run(command, shell=False, check=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore-test a backup file into an isolated database, then drop it")
    parser.add_argument("--backup-id", type=int, default=None, help="backups.id to test; defaults to the latest backup")
    parser.add_argument("--keep", action="store_true", help="Keep the restored test database (default: drop after test)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.backup_id:
            backup = db.get(Backup, args.backup_id)
        else:
            backup = db.query(Backup).filter(Backup.status == "success").order_by(Backup.created_at.desc()).first()
        if not backup:
            print("No successful backup found.", file=sys.stderr)
            return 1

        candidate = storage_service.safe_backup_path(backup.relative_path or backup.filename)
        if candidate is None or not candidate.exists():
            print(f"Backup file missing: {backup.filename}", file=sys.stderr)
            return 1

        client = find_mysql_client()
        with tempfile.TemporaryDirectory(prefix="dbmonitor_restore_") as tmp:
            tmp_dir = Path(tmp)
            defaults = write_defaults(tmp_dir)
            table_count = 0
            try:
                run_mysql(
                    client,
                    defaults,
                    None,
                    ["-e", f"DROP DATABASE IF EXISTS `{TEST_DATABASE}`; CREATE DATABASE `{TEST_DATABASE}` CHARACTER SET utf8mb4;"],
                )
                run_mysql(client, defaults, TEST_DATABASE, [], stdin_path=candidate)
                result = subprocess.run(
                    [str(client), f"--defaults-extra-file={defaults}", "-N", "-e",
                     f"SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='{TEST_DATABASE}';"],
                    shell=False,
                    check=True,
                    capture_output=True,
                )
                table_count = int(result.stdout.decode().strip() or "0")
            finally:
                if not args.keep:
                    try:
                        run_mysql(client, defaults, None, ["-e", f"DROP DATABASE IF EXISTS `{TEST_DATABASE}`;"])
                    except subprocess.CalledProcessError:
                        print(f"Warning: could not drop {TEST_DATABASE}", file=sys.stderr)

        audit_service.log_event(
            db,
            actor="restore_test",
            action="backup_restore_tested",
            status="success",
            database_name=backup.database_name,
            filename=backup.filename,
            detail=f"Restored into isolated database; {table_count} tables; keep={args.keep}",
        )
        print(f"OK: restore test passed ({table_count} tables restored into {TEST_DATABASE}).")
        return 0
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
        audit_service.log_event(
            db,
            actor="restore_test",
            action="backup_restore_tested",
            status="failed",
            detail=stderr[:2000],
        )
        print(f"FAILED: restore test failed: {stderr[:500]}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
