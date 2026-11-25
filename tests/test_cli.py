"""CLI end-to-end tests."""

import json
import os

import pytest

from sql_eval_analytics.cli import main
from tests.conftest import DATA_DIR


def test_load_creates_db_with_counts(tmp_path, capsys):
    db = tmp_path / "eval.db"
    assert main(["load", "--data", str(DATA_DIR), "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "Loaded 428 rows into 6 tables (sqlite)" in out
    assert "annotations: 122" in out
    assert db.exists()
    # Loading again rebuilds cleanly.
    assert main(["load", "--data", str(DATA_DIR), "--db", str(db)]) == 0


def test_query_text_and_json(tmp_path, capsys):
    db = tmp_path / "eval.db"
    assert main(["load", "--data", str(DATA_DIR), "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["query", "--db", str(db), "--name", "annotator_agreement"]) == 0
    out = capsys.readouterr().out
    assert "annotator_agreement" in out
    assert "cohens_kappa" in out
    assert "0.643" in out
    assert main(["query", "--db", str(db), "--name", "annotator_agreement", "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["annotator_agreement"]["rows"][0]["project"] == "ALL"


def test_query_postgres_only_skips_on_sqlite(tmp_path, capsys):
    db = tmp_path / "eval.db"
    assert main(["load", "--data", str(DATA_DIR), "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["query", "--db", str(db), "--name", "median_review_turnaround"]) == 0
    assert "skipped" in capsys.readouterr().err


def test_report_from_data_dir(capsys):
    assert main(["report", "--data", str(DATA_DIR)]) == 0
    out = capsys.readouterr().out
    for name in (
        "annotator_agreement",
        "annotator_throughput",
        "review_turnaround",
        "quality_reject_rates",
        "score_calibration",
        "weekly_trends",
        "duplicate_submissions",
        "reviewer_workload",
        "annotator_confidence_vs_accuracy",
        "median_review_turnaround",
    ):
        assert f"== {name} ==" in out
    assert "0.643" in out
    assert "(skipped: PostgreSQL-only" in out


def test_report_json_parses(capsys):
    assert main(["report", "--data", str(DATA_DIR), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert len(parsed) == 10
    assert parsed["duplicate_submissions"]["rows"][0]["item_id"] == "itm-003"


def test_list_shows_all_queries(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "annotator_agreement" in out
    assert "median_review_turnaround [PostgreSQL-only]" in out


def test_unknown_query_exits_two(tmp_path, capsys):
    db = tmp_path / "eval.db"
    assert main(["load", "--data", str(DATA_DIR), "--db", str(db)]) == 0
    assert main(["query", "--db", str(db), "--name", "nope"]) == 2
    assert "unknown query" in capsys.readouterr().err


def test_missing_db_file_exits_two(capsys):
    assert main(["report", "--db", "/nonexistent/eval.db"]) == 2
    assert "no database" in capsys.readouterr().err


def test_missing_data_dir_exits_two(tmp_path):
    assert main(["load", "--data", str(tmp_path / "missing"), "--db", str(tmp_path / "x.db")]) == 2


def test_postgres_without_database_url_exits_two(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["--postgres", "report"]) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_postgres_flag_after_subcommand(monkeypatch, capsys):
    # --postgres is accepted after the subcommand as well.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert main(["report", "--postgres"]) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err
