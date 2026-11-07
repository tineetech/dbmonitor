import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class BackupCreateRequest(BaseModel):
    database_name: str = Field(min_length=1, max_length=64)
    ephemeral: bool = False


class ScheduleCreateRequest(BaseModel):
    database_name: str = Field(min_length=1, max_length=64)
    frequency: str = Field(default="daily")
    run_time: str = Field(default="02:00")
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    enabled: bool = True

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        if value not in {"daily", "weekly"}:
            raise ValueError("frequency must be 'daily' or 'weekly'")
        return value

    @field_validator("run_time")
    @classmethod
    def validate_time(cls, value: str) -> str:
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            raise ValueError("run_time must be in HH:MM format (00:00-23:59)")
        return value


class ScheduleUpdateRequest(BaseModel):
    frequency: Optional[str] = None
    run_time: Optional[str] = None
    day_of_week: Optional[int] = Field(default=None, ge=0, le=6)
    enabled: Optional[bool] = None

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"daily", "weekly"}:
            raise ValueError("frequency must be 'daily' or 'weekly'")
        return value

    @field_validator("run_time")
    @classmethod
    def validate_time(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", value):
            raise ValueError("run_time must be in HH:MM format (00:00-23:59)")
        return value


class SettingsUpdateRequest(BaseModel):
    storage_warn_pct: Optional[int] = Field(default=None, ge=1, le=100)
    storage_critical_pct: Optional[int] = Field(default=None, ge=1, le=100)
    retention_days: Optional[int] = Field(default=None, ge=0, le=3650)
    max_concurrent_backups: Optional[int] = Field(default=None, ge=1, le=10)
