"""Schema loading and connection helpers."""

from __future__ import annotations

import os
import sqlite3
from importlib import resources

from .dialect import translate_for_sqlite

DIALECT_SQLITE = "sqlite"
DIALECT_POSTGRES = "postgres"


def load_schema_sql() -> str:
    """The canonical PostgreSQL schema (schema.sql, shipped with the package)."""
    return resources.files("sql_eval_analytics").joinpath("schema.sql").read_text(
        encoding="utf-8"
    )


def connect_sqlite(path: str) -> sqlite3.Connection:
    """Open a SQLite database with foreign keys enforced."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_postgres():
    """Connect to PostgreSQL from the DATABASE_URL environment variable.

    No credential is ever read from a file in the repo. psycopg is an
    optional extra (pip install -e '.[postgres]'); without it this raises a
    clear error instead of failing at import time.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Export it before using --postgres, "
            "for example: export DATABASE_URL=postgresql://user@host:5432/db"
        )
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised in tests via a fake module
        raise RuntimeError(
            "psycopg is not installed. Install the postgres extra: "
            "pip install -e '.[postgres]'"
        ) from exc
    return psycopg.connect(url)


def drop_tables(conn, dialect: str) -> None:
    """Drop all tables in reverse dependency order (load rebuilds the DB)."""
    tables = ["scores", "reviews", "eval_runs", "annotations", "annotation_items", "annotators"]
    cur = conn.cursor()
    for table in tables:
        cur.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()


def create_schema(conn, dialect: str) -> None:
    """Create the schema on either engine (translating DDL for SQLite)."""
    sql = load_schema_sql()
    if dialect == DIALECT_SQLITE:
        sql = translate_for_sqlite(sql)
    if dialect == DIALECT_SQLITE:
        conn.executescript(sql)
    else:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
