"""Command line: sqleval load | query | report | list.

Examples (local engine, SQLite):

    sqleval load --data data/examples --db eval.db
    sqleval query --db eval.db --name annotator_agreement
    sqleval report --db eval.db
    sqleval report --data data/examples        # build in memory, no file
    sqleval list

Against a real PostgreSQL server (psycopg extra required, connection from
the DATABASE_URL environment variable only — never a flag, never a file):

    export DATABASE_URL=postgresql://user@host:5432/db
    sqleval --postgres load --data data/examples
    sqleval --postgres report
"""

from __future__ import annotations

import argparse
import os
import sys

from . import queries as query_mod
from .loader import load_csvs
from .report import render_json, render_text
from .schema import (
    connect_postgres,
    connect_sqlite,
    create_schema,
    drop_tables,
)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--postgres",
        action="store_true",
        # SUPPRESS so a subparser default cannot overwrite a --postgres
        # given before the subcommand (argparse applies subparser defaults
        # after the top-level parse).
        default=argparse.SUPPRESS,
        help="run against PostgreSQL via DATABASE_URL instead of SQLite",
    )
    parser = argparse.ArgumentParser(
        prog="sqleval",
        description="SQL analytics for AI evaluation operations data.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    load_p = sub.add_parser("load", parents=[common], help="build a database from CSVs")
    load_p.add_argument("--data", required=True, help="directory of CSV files")
    load_p.add_argument("--db", default="eval.db", help="SQLite file (ignored with --postgres)")

    query_p = sub.add_parser("query", parents=[common], help="run one query")
    query_p.add_argument("--db", default="eval.db")
    query_p.add_argument("--data", help="build an in-memory DB from this CSV directory instead")
    query_p.add_argument("--name", required=True, help="query name (see: sqleval list)")
    query_p.add_argument("--json", action="store_true", help="print JSON instead of a table")

    report_p = sub.add_parser("report", parents=[common], help="run every query")
    report_p.add_argument("--db", default="eval.db")
    report_p.add_argument("--data", help="build an in-memory DB from this CSV directory instead")
    report_p.add_argument("--json", action="store_true", help="print JSON instead of text")

    sub.add_parser("list", parents=[common], help="list the available queries")
    return parser


def _open(args):
    """Return (connection, dialect) for the requested engine."""
    if getattr(args, "postgres", False):
        return connect_postgres(), "postgres"
    if getattr(args, "data", None):
        conn = connect_sqlite(":memory:")
        create_schema(conn, "sqlite")
        load_csvs(conn, args.data, "sqlite")
        return conn, "sqlite"
    db = getattr(args, "db", "eval.db")
    if not os.path.exists(db):
        raise FileNotFoundError(
            f"no database at {db!r}. Build one first: "
            f"sqleval load --data data/examples --db {db}"
        )
    return connect_sqlite(db), "sqlite"


def _cmd_load(args) -> int:
    if getattr(args, "postgres", False):
        conn, dialect = connect_postgres(), "postgres"
    else:
        conn, dialect = connect_sqlite(args.db), "sqlite"
    drop_tables(conn, dialect)
    create_schema(conn, dialect)
    counts = load_csvs(conn, args.data, dialect)
    total = sum(counts.values())
    print(f"Loaded {total} rows into {len(counts)} tables ({dialect}):")
    for table, n in counts.items():
        print(f"  {table}: {n}")
    return 0


def _cmd_query(args) -> int:
    conn, dialect = _open(args)
    query = query_mod.get_query(args.name)
    try:
        rows = query_mod.run_query(conn, query, dialect)
    except query_mod.PostgresOnlyError as exc:
        print(f"sqleval: skipped: {exc}", file=sys.stderr)
        return 0
    if args.json:
        print(render_json({query.name: {"rows": rows}}), end="")
    else:
        from .report import render_table

        print(f"== {query.name} ==")
        print(query.question)
        print(render_table(rows))
    return 0


def _cmd_report(args) -> int:
    conn, dialect = _open(args)
    results = query_mod.run_all(conn, dialect)
    questions = {q.name: q.question for q in query_mod.list_queries()}
    if args.json:
        print(render_json(results), end="")
    else:
        print(render_text(results, questions), end="")
    return 0


def _cmd_list(_args) -> int:
    for query in query_mod.list_queries():
        tag = " [PostgreSQL-only]" if query.postgres_only else ""
        print(f"{query.name}{tag}\n  {query.question}")
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "load":
            return _cmd_load(args)
        if args.command == "query":
            return _cmd_query(args)
        if args.command == "report":
            return _cmd_report(args)
        if args.command == "list":
            return _cmd_list(args)
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"sqleval: error: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
