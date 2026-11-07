from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import settings
from app.database import engine


def _connection() -> Connection:
    return engine.connect()


def get_server_status() -> dict:
    try:
        with _connection() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
            conn.execute(text("SELECT 1"))
        return {"connected": True, "version": str(version)}
    except Exception:
        return {"connected": False, "version": None}


def list_database_names(show_system: bool = False) -> list[str]:
    with _connection() as conn:
        if show_system:
            rows = conn.execute(text("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA")).scalars().all()
        else:
            placeholders = ", ".join(f":s{i}" for i in range(len(settings.SYSTEM_SCHEMAS)))
            params = {f"s{i}": name for i, name in enumerate(settings.SYSTEM_SCHEMAS)}
            rows = (
                conn.execute(
                    text(f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME NOT IN ({placeholders})"),
                    params,
                )
                .scalars()
                .all()
            )
    return sorted(str(name) for name in rows)


def is_known_database(name: str, show_system: bool = False) -> bool:
    if not name:
        return False
    try:
        names = list_database_names(show_system=show_system)
    except Exception:
        return False
    return name in names


def get_database_overview(show_system: bool = False) -> list[dict]:
    names = list_database_names(show_system=show_system)
    if not names:
        return []
    placeholders = ", ".join(f":n{i}" for i in range(len(names)))
    params = {f"n{i}": name for i, name in enumerate(names)}
    query = text(
        f"""
        SELECT TABLE_SCHEMA AS schema_name,
               COUNT(*) AS table_count,
               COALESCE(SUM(COALESCE(DATA_LENGTH, 0)), 0) AS data_length,
               COALESCE(SUM(COALESCE(INDEX_LENGTH, 0)), 0) AS index_length,
               MAX(COALESCE(DATA_LENGTH, 0) + COALESCE(INDEX_LENGTH, 0)) AS largest_table
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA IN ({placeholders})
        GROUP BY TABLE_SCHEMA
        """
    )
    collation_query = text(
        f"""
        SELECT SCHEMA_NAME AS schema_name, DEFAULT_CHARACTER_SET_NAME AS charset,
               DEFAULT_COLLATION_NAME AS collation
        FROM information_schema.SCHEMATA
        WHERE SCHEMA_NAME IN ({placeholders})
        """
    )
    with _connection() as conn:
        table_stats = {row.schema_name: row for row in conn.execute(query, params).mappings()}
        charset_stats = {row.schema_name: row for row in conn.execute(collation_query, params).mappings()}

    result = []
    for name in names:
        stat = table_stats.get(name)
        cs = charset_stats.get(name)
        data_length = int(stat["data_length"]) if stat else 0
        index_length = int(stat["index_length"]) if stat else 0
        result.append(
            {
                "name": name,
                "table_count": int(stat["table_count"]) if stat else 0,
                "data_length": data_length,
                "index_length": index_length,
                "total_size": data_length + index_length,
                "charset": cs["charset"] if cs else None,
                "collation": cs["collation"] if cs else None,
            }
        )
    result.sort(key=lambda item: item["total_size"], reverse=True)
    return result


def get_database_detail(name: str) -> Optional[dict]:
    overview = {db["name"]: db for db in get_database_overview(show_system=True)}
    detail = overview.get(name)
    if detail is None:
        return None
    with _connection() as conn:
        engine_counts = (
            conn.execute(
                text(
                    """
                    SELECT COALESCE(ENGINE, 'unknown') AS engine, COUNT(*) AS table_count
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = :schema
                    GROUP BY ENGINE
                    """
                ),
                {"schema": name},
            )
            .mappings()
            .all()
        )
    engines = [{"engine": row["engine"], "table_count": int(row["table_count"])} for row in engine_counts]
    non_transactional = [row["engine"] for row in engines if row["engine"].upper() in {"MYISAM", "CSV", "HEAP", "MEMORY", "ARCHIVE"}]
    detail = dict(detail)
    detail["engines"] = engines
    detail["has_non_transactional"] = bool(non_transactional)
    detail["non_transactional_engines"] = non_transactional
    return detail


def list_tables(
    name: str,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 10,
) -> Optional[dict]:
    with _connection() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = :schema"),
            {"schema": name},
        ).scalar()
        if not exists:
            return None
        where = "TABLE_SCHEMA = :schema"
        params: dict = {"schema": name}
        if search:
            where += " AND TABLE_NAME LIKE :search"
            params["search"] = f"%{search}%"
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM information_schema.TABLES WHERE {where}"),
            params,
        ).scalar() or 0
        offset = max(0, (page - 1) * per_page)
        rows = (
            conn.execute(
                text(
                    f"""
                    SELECT TABLE_NAME AS table_name, ENGINE AS engine, TABLE_ROWS AS table_rows,
                           COALESCE(DATA_LENGTH, 0) AS data_length,
                           COALESCE(INDEX_LENGTH, 0) AS index_length,
                           COALESCE(DATA_LENGTH, 0) + COALESCE(INDEX_LENGTH, 0) AS total_size,
                           TABLE_COLLATION AS table_collation
                    FROM information_schema.TABLES
                    WHERE {where}
                    ORDER BY total_size DESC, table_name ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {**params, "limit": per_page, "offset": offset},
            )
            .mappings()
            .all()
        )
    tables = [
        {
            "table_name": row["table_name"],
            "engine": row["engine"],
            "table_rows": int(row["table_rows"]) if row["table_rows"] is not None else None,
            "data_length": int(row["data_length"]),
            "index_length": int(row["index_length"]),
            "total_size": int(row["total_size"]),
            "collation": row["table_collation"],
        }
        for row in rows
    ]
    total_pages = max(1, (int(total) + per_page - 1) // per_page)
    return {
        "database": name,
        "total": int(total),
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "tables": tables,
    }


def get_database_sizes_map(show_system: bool = False) -> dict[str, int]:
    return {db["name"]: db["total_size"] for db in get_database_overview(show_system=show_system)}


def get_table_counts_map(show_system: bool = False) -> dict[str, int]:
    return {db["name"]: db["table_count"] for db in get_database_overview(show_system=show_system)}
