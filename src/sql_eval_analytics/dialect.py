"""PostgreSQL -> SQLite translation.

The canonical SQL in this repo is PostgreSQL. The local engine is SQLite,
so the small set of constructs SQLite does not have is rewritten here, in
one place, with the mapping documented in the docstring of each rule.
Anything outside the mapping raises instead of silently running something
different — a wrong number is worse than a loud failure.
"""

from __future__ import annotations

import re

_DATE_TRUNC_RE = re.compile(r"date_trunc\('(\w+)',\s*([\w.]+)\)")
_EXTRACT_EPOCH_RE = re.compile(
    r"EXTRACT\s*\(\s*EPOCH\s+FROM\s+\(\s*([\w.]+)\s*-\s*([\w.]+)\s*\)\s*\)"
)


def _replace_date_trunc(match: re.Match[str]) -> str:
    unit, column = match.group(1), match.group(2)
    # PostgreSQL date_trunc('week', x) is the Monday 00:00 of x's week.
    # SQLite: 'weekday 0' advances to the Sunday of x's week, minus 6 days
    # is the Monday. Sunday itself stays put, so it lands on the previous
    # Monday — the same week PostgreSQL assigns it to.
    if unit == "week":
        return f"date({column}, 'weekday 0', '-6 days')"
    if unit == "day":
        return f"date({column})"
    if unit == "month":
        return f"date({column}, 'start of month')"
    raise ValueError(f"date_trunc unit {unit!r} has no SQLite translation")


def _replace_extract_epoch(match: re.Match[str]) -> str:
    first, second = match.group(1), match.group(2)
    # EXTRACT(EPOCH FROM (a - b)) is the interval in seconds. julianday
    # differences are in days; * 86400 is the same number of seconds.
    return f"(julianday({first}) - julianday({second})) * 86400"


def _strip_comments(sql: str) -> str:
    """SQL without -- comments, for the guard checks below.

    Query headers legitimately name constructs (e.g. percentile_cont) in
    prose; only the executable SQL matters. No query in this repo has --
    inside a string literal.
    """
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def translate_for_sqlite(sql: str) -> str:
    """Rewrite PostgreSQL SQL so it runs unchanged in meaning on SQLite."""
    out = sql
    # DDL: SERIAL becomes an autoincrementing integer key; TIMESTAMPTZ
    # becomes TEXT holding the same ISO-8601 strings (SQLite's date
    # functions accept them, and PostgreSQL parses them as timestamps).
    out = out.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    out = out.replace("TIMESTAMPTZ", "TEXT")
    out = _DATE_TRUNC_RE.sub(_replace_date_trunc, out)
    out = _EXTRACT_EPOCH_RE.sub(_replace_extract_epoch, out)
    code = _strip_comments(out)
    if "date_trunc(" in code:
        raise ValueError("untranslated date_trunc remains in SQL for SQLite")
    if "EXTRACT(EPOCH" in code:
        raise ValueError("untranslated EXTRACT(EPOCH ...) remains in SQL for SQLite")
    if "percentile_cont" in code:
        raise ValueError("percentile_cont has no SQLite equivalent")
    return out
