"""PostgreSQL connection pool and small query helpers (psycopg 3)."""
from __future__ import annotations

import contextlib
from typing import Any, Iterable, Optional

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_config

_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        cfg = get_config()
        _pool = ConnectionPool(
            conninfo=cfg.dsn,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
        )
    return _pool


@contextlib.contextmanager
def connection():
    """A transactional connection: commits on success, rolls back on error."""
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def query_all(sql: str, params: Iterable[Any] | None = None) -> list[dict]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql: str, params: Iterable[Any] | None = None) -> Optional[dict]:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute(sql: str, params: Iterable[Any] | None = None) -> int:
    with connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount
