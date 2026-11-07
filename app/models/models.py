from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base
from app.utils import now


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="super_admin")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=now)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    database_name = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    requested_by = Column(String(64), nullable=False, default="system")
    is_ephemeral = Column(Boolean, nullable=False, default=False)
    file_id = Column(Integer, ForeignKey("backups.id", ondelete="SET NULL"), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now, index=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    worker_id = Column(String(64), nullable=True)

    backup_file = relationship("Backup", back_populates="job")


class Backup(Base):
    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), unique=True, nullable=False, index=True)
    database_name = Column(String(64), nullable=False, index=True)
    relative_path = Column(String(500), nullable=False, default="")
    file_size = Column(BigInteger, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False, default="")
    status = Column(String(20), nullable=False, default="success", index=True)
    is_ephemeral = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=now, index=True)

    job = relationship("BackupJob", back_populates="backup_file", uselist=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    database_name = Column(String(64), nullable=True)
    filename = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)
    status = Column(String(20), nullable=False, default="success", index=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=now, index=True)


class DatabaseSizeSnapshot(Base):
    __tablename__ = "database_size_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    database_name = Column(String(64), nullable=False, index=True)
    total_bytes = Column(BigInteger, nullable=False, default=0)
    table_count = Column(Integer, nullable=False, default=0)
    captured_at = Column(DateTime, nullable=False, default=now, index=True)


class HostResourceSnapshot(Base):
    __tablename__ = "host_resource_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, nullable=False, default=now, index=True)
    ram_total_bytes = Column(BigInteger, nullable=False, default=0)
    ram_used_bytes = Column(BigInteger, nullable=False, default=0)
    ram_percent = Column(Float, nullable=False, default=0.0)
    cpu_percent = Column(Float, nullable=False, default=0.0)
    cpu_count = Column(Integer, nullable=False, default=0)
    load_avg_1m = Column(Float, nullable=True)
    load_avg_5m = Column(Float, nullable=True)
    load_avg_15m = Column(Float, nullable=True)


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    database_name = Column(String(64), nullable=False)
    frequency = Column(String(10), nullable=False, default="daily")
    run_time = Column(String(5), nullable=False, default="02:00")
    day_of_week = Column(Integer, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_by = Column(String(64), nullable=False, default="system")
    created_at = Column(DateTime, nullable=False, default=now)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, nullable=False, default=now, onupdate=now)

