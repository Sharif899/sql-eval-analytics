"""Schema and dialect-translation tests."""

import sqlite3

import pytest

from sql_eval_analytics.dialect import translate_for_sqlite
from sql_eval_analytics.loader import load_csvs
from sql_eval_analytics.schema import connect_sqlite, create_schema, drop_tables

EXPECTED_TABLES = {
    "annotators",
    "annotation_items",
    "annotations",
    "reviews",
    "eval_runs",
    "scores",
}


def test_all_tables_created(db):
    names = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert EXPECTED_TABLES <= names


def test_indexes_created(db):
    indexes = {
        row[1]
        for row in db.execute("SELECT type, name FROM sqlite_master WHERE type = 'index'")
    }
    assert "idx_annotations_item" in indexes
    assert "idx_annotations_annotator" in indexes
    assert "idx_reviews_annotation" in indexes
    assert "idx_scores_run" in indexes


def test_foreign_key_violation_fails(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO annotations (annotation_id, item_id, annotator_id, label,"
            " confidence, submitted_at) VALUES (999, 'itm-999', 'A01', 'correct', 0.9,"
            " '2026-01-05 10:00:00')"
        )


def test_check_constraint_violation_fails(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO annotations (annotation_id, item_id, annotator_id, label,"
            " confidence, submitted_at) VALUES (998, 'itm-001', 'A01', 'bogus', 0.9,"
            " '2026-01-05 10:00:00')"
        )


def test_load_twice_is_idempotent(data_dir):
    conn = connect_sqlite(":memory:")
    for _ in range(2):
        drop_tables(conn, "sqlite")
        create_schema(conn, "sqlite")
        counts = load_csvs(conn, data_dir, "sqlite")
    assert counts == {
        "annotators": 8,
        "annotation_items": 60,
        "annotations": 122,
        "reviews": 116,
        "eval_runs": 2,
        "scores": 120,
    }
    conn.close()


def test_translated_schema_has_no_postgres_only_ddl():
    from sql_eval_analytics.dialect import _strip_comments
    from sql_eval_analytics.schema import load_schema_sql

    # The header comment legitimately names the constructs; only the
    # executable DDL must be free of them.
    translated = _strip_comments(translate_for_sqlite(load_schema_sql()))
    assert "SERIAL" not in translated
    assert "TIMESTAMPTZ" not in translated


def test_date_trunc_week_translation():
    assert (
        translate_for_sqlite("SELECT date_trunc('week', submitted_at) FROM t")
        == "SELECT date(submitted_at, 'weekday 0', '-6 days') FROM t"
    )
    assert (
        translate_for_sqlite("SELECT date_trunc('day', x), date_trunc('month', x) FROM t")
        == "SELECT date(x), date(x, 'start of month') FROM t"
    )


def test_extract_epoch_translation():
    out = translate_for_sqlite(
        "SELECT EXTRACT(EPOCH FROM (r.reviewed_at - a.submitted_at)) / 3600.0 FROM t"
    )
    assert out == (
        "SELECT (julianday(r.reviewed_at) - julianday(a.submitted_at)) * 86400 / 3600.0 FROM t"
    )


def test_unknown_date_trunc_unit_raises():
    with pytest.raises(ValueError, match="date_trunc unit 'quarter'"):
        translate_for_sqlite("SELECT date_trunc('quarter', x) FROM t")


def test_percentile_cont_raises():
    with pytest.raises(ValueError, match="percentile_cont"):
        translate_for_sqlite("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY x) FROM t")


def test_week_start_is_monday(db):
    # date_trunc('week') is Monday-start; the SQLite translation must agree.
    cases = {
        "2026-01-05 10:00:00": "2026-01-05",  # Monday
        "2026-01-11 10:00:00": "2026-01-05",  # Sunday belongs to the same week
        "2026-01-12 10:00:00": "2026-01-12",  # next Monday
        "2026-02-16 09:00:00": "2026-02-16",
    }
    for given, monday in cases.items():
        got = db.execute(
            "SELECT date(?, 'weekday 0', '-6 days')", (given,)
        ).fetchone()[0]
        assert got == monday, f"{given} -> {got}, expected {monday}"


def test_postgres_connection_requires_database_url(monkeypatch):
    from sql_eval_analytics.schema import connect_postgres

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        connect_postgres()
