"""Forward-only, checksum-guarded migration runner.

Scans backend/migrations/*.sql in order, applies unapplied files inside a
transaction, and records filename + checksum. Refuses to run on drift.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

import psycopg

from .config import get_config

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_migrations() -> None:
    cfg = get_config()
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("[migrate] no migration files found", flush=True)
        return

    with psycopg.connect(cfg.dsn, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(_BOOTSTRAP)
        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT filename, checksum FROM schema_migrations")
            applied = {row[0]: row[1] for row in cur.fetchall()}

        for path in files:
            name = path.name
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)

            if name in applied:
                if applied[name] != checksum:
                    raise SystemExit(
                        f"[migrate] FATAL: checksum drift on already-applied "
                        f"migration {name}. Refusing to start."
                    )
                continue

            print(f"[migrate] applying {name}", flush=True)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (filename, checksum) "
                        "VALUES (%s, %s)",
                        (name, checksum),
                    )
                conn.commit()
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f"[migrate] FAILED on {name}: {exc}", file=sys.stderr, flush=True)
                raise

    print("[migrate] all migrations applied", flush=True)
