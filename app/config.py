import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_DEBUG: bool = _bool("APP_DEBUG", False)
    APP_SECRET_KEY: str = os.getenv("APP_SECRET_KEY", "")

    DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT: int = _int("DB_PORT", 3306)
    DB_NAME: str = os.getenv("DB_NAME", "db_monitor_app")
    DB_USERNAME: str = os.getenv("DB_USERNAME", "db_monitor")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    MYSQL_DUMP_PATH: str = os.getenv("MYSQL_DUMP_PATH", "")
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "storage/backups")
    BACKUP_RETENTION_DAYS: int = _int("BACKUP_RETENTION_DAYS", 30)
    BACKUP_TIMEOUT_SECONDS: int = _int("BACKUP_TIMEOUT_SECONDS", 3600)
    MAX_CONCURRENT_BACKUPS: int = max(1, _int("MAX_CONCURRENT_BACKUPS", 1))
    EPHEMERAL_TTL_MINUTES: int = max(1, _int("EPHEMERAL_TTL_MINUTES", 15))

    SESSION_COOKIE_SECURE: bool = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_EXPIRE_MINUTES: int = _int("SESSION_EXPIRE_MINUTES", 480)

    SHOW_SYSTEM_DATABASES: bool = _bool("SHOW_SYSTEM_DATABASES", False)
    STORAGE_WARN_PCT: int = _int("STORAGE_WARN_PCT", 70)
    STORAGE_CRITICAL_PCT: int = _int("STORAGE_CRITICAL_PCT", 85)
    MONITORING_REFRESH_SECONDS: int = _int("MONITORING_REFRESH_SECONDS", 60)
    APP_TIMEZONE_OFFSET_HOURS: int = _int("APP_TIMEZONE_OFFSET_HOURS", 7)

    SYSTEM_SCHEMAS = ("information_schema", "performance_schema", "mysql", "sys")

    def __init__(self) -> None:
        if not self.APP_SECRET_KEY or self.APP_SECRET_KEY == "replace-with-strong-secret":
            raise RuntimeError(
                "APP_SECRET_KEY is not set or uses the placeholder. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        self.backup_dir = self._resolve_path(self.BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / "storage" / "logs").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_path(value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    def resolve_dump_binary(self) -> str:
        configured = self.MYSQL_DUMP_PATH.strip().strip('"')
        candidates = []
        if configured:
            p = Path(configured)
            if p.is_dir():
                candidates += [
                    p / "mysqldump.exe",
                    p / "mariadb-dump.exe",
                    p / "mysqldump",
                    p / "mariadb-dump",
                ]
            else:
                candidates.append(p)
        for name in ("mysqldump", "mariadb-dump"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)
        raise FileNotFoundError(
            "Dump binary not found. Set MYSQL_DUMP_PATH in .env to mysqldump/mariadb-dump."
        )

    @property
    def database_url(self) -> str:
        from urllib.parse import quote_plus

        return (
            f"mysql+pymysql://{quote_plus(self.DB_USERNAME)}:{quote_plus(self.DB_PASSWORD)}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )


settings = Settings()
