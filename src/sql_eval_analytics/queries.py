"""Query registry: the .sql files are the source of truth.

Each query file starts with a header comment declaring its name, the
question it answers, and its dialect ("postgres" runs on SQLite through the
translation in dialect.py; "postgres-only" needs a real PostgreSQL server).
The registry reads those headers, so adding a query is adding a file — no
Python change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from importlib import resources

from .dialect import translate_for_sqlite

DIALECT_POSTGRES = "postgres"
DIALECT_POSTGRES_ONLY = "postgres-only"


class PostgresOnlyError(RuntimeError):
    """A query that needs PostgreSQL was asked to run on SQLite."""


@dataclass(frozen=True)
class Query:
    name: str
    question: str
    dialect: str
    sql: str

    @property
    def postgres_only(self) -> bool:
        return self.dialect == DIALECT_POSTGRES_ONLY


def _parse_header(text: str) -> tuple[str, str, str]:
    name = ""
    question_parts: list[str] = []
    dialect = DIALECT_POSTGRES
    in_question = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("--"):
            break
        body = stripped[2:].strip()
        if body.startswith("name:"):
            name = body[len("name:"):].strip()
            in_question = False
        elif body.startswith("dialect:"):
            raw = body[len("dialect:"):].strip()
            dialect = (
                DIALECT_POSTGRES_ONLY if raw.startswith("postgres-only") else DIALECT_POSTGRES
            )
            in_question = False
        elif body.startswith("question:"):
            question_parts.append(body[len("question:"):].strip())
            in_question = True
        elif in_question and body:
            question_parts.append(body)
        elif in_question and not body:
            in_question = False
    if not name:
        raise ValueError("query file is missing a '-- name:' header")
    return name, " ".join(question_parts), dialect


def list_queries() -> list[Query]:
    """All queries, sorted by name (portable ones first, then postgres-only)."""
    base = resources.files("sql_eval_analytics") / "queries"
    found: list[Query] = []
    for path in sorted(base.rglob("*.sql")):
        text = path.read_text(encoding="utf-8")
        name, question, dialect = _parse_header(text)
        found.append(Query(name=name, question=question, dialect=dialect, sql=text))
    found.sort(key=lambda q: (q.postgres_only, q.name))
    return found


def get_query(name: str) -> Query:
    queries = {q.name: q for q in list_queries()}
    if name not in queries:
        available = ", ".join(sorted(queries))
        raise KeyError(f"unknown query {name!r}; available: {available}")
    return queries[name]


def _normalize(value):
    """Make result values identical across engines for reporting.

    PostgreSQL returns timestamps as datetimes; SQLite returns the same
    instants as ISO strings. A Monday 00:00 week start becomes the date
    string on both, so reports read the same either way.
    """
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0 and value.second == 0:
            return value.date().isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def run_query(conn, query: Query, dialect: str) -> list[dict]:
    """Run one query and return rows as a list of dicts."""
    if query.postgres_only and dialect != DIALECT_POSTGRES:
        raise PostgresOnlyError(
            f"query {query.name!r} needs PostgreSQL (it uses percentile_cont, "
            "which SQLite does not have). Run it with --postgres or psql."
        )
    sql = query.sql
    if dialect != DIALECT_POSTGRES:
        sql = translate_for_sqlite(sql)
    cur = conn.cursor()
    cur.execute(sql)
    columns = [d[0] for d in cur.description]
    return [
        {col: _normalize(value) for col, value in zip(columns, row)}
        for row in cur.fetchall()
    ]


def run_all(conn, dialect: str) -> dict[str, dict]:
    """Run every query. Postgres-only queries are reported as skipped."""
    results: dict[str, dict] = {}
    for query in list_queries():
        if query.postgres_only and dialect != DIALECT_POSTGRES:
            results[query.name] = {
                "skipped": "PostgreSQL-only (percentile_cont); run with --postgres.",
                "rows": [],
            }
        else:
            results[query.name] = {"rows": run_query(conn, query, dialect)}
    return results
