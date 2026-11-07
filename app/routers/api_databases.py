from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.dependencies import get_current_full_access, get_current_user
from app.services import mysql_service

router = APIRouter(prefix="/api/v1/databases", tags=["databases"])


def _validated_name_or_404(name: str) -> str:
    if not mysql_service.is_known_database(name, show_system=settings.SHOW_SYSTEM_DATABASES):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return name


@router.get("")
def list_databases(
    search: Optional[str] = Query(default=None, max_length=64),
    sort: str = Query(default="total_size", max_length=20),
    order: str = Query(default="desc", max_length=4),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    del user
    overview = mysql_service.get_database_overview(show_system=settings.SHOW_SYSTEM_DATABASES)
    if search:
        needle = search.strip().lower()
        overview = [item for item in overview if needle in item["name"].lower()]

    reverse = order != "asc"
    if sort == "name":
        overview.sort(key=lambda item: item["name"].lower(), reverse=reverse)
    elif sort == "table_count":
        overview.sort(key=lambda item: item["table_count"], reverse=reverse)
    elif sort == "data_length":
        overview.sort(key=lambda item: item["data_length"], reverse=reverse)
    else:
        overview.sort(key=lambda item: item["total_size"], reverse=reverse)
    total = len(overview)
    start = (page - 1) * per_page
    page_items = overview[start : start + per_page]
    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "databases": page_items,
    }


@router.get("/{name}")
def database_detail(name: str, user: dict = Depends(get_current_full_access)):
    del user
    _validated_name_or_404(name)
    detail = mysql_service.get_database_detail(name)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return detail


@router.get("/{name}/tables")
def database_tables(
    name: str,
    search: Optional[str] = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    user: dict = Depends(get_current_full_access),
):
    del user
    _validated_name_or_404(name)
    result = mysql_service.list_tables(name, search=search, page=page, per_page=per_page)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database not found")
    return result


@router.get("/{name}/engines")
def database_engines(name: str, user: dict = Depends(get_current_full_access)):
    del user
    _validated_name_or_404(name)
    detail = mysql_service.get_database_detail(name)
    return {
        "database": name,
        "engines": detail["engines"] if detail else [],
        "has_non_transactional": detail["has_non_transactional"] if detail else False,
        "non_transactional_engines": detail["non_transactional_engines"] if detail else [],
    }
