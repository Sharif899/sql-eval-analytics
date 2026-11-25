"""Shared fixtures: an in-memory database loaded with the example data."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sql_eval_analytics.loader import load_csvs
from sql_eval_analytics.schema import connect_sqlite, create_schema

PROJECT_ROOT = Path(__file__).parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "examples"


@pytest.fixture()
def data_dir():
    return DATA_DIR


@pytest.fixture()
def db():
    conn = connect_sqlite(":memory:")
    create_schema(conn, "sqlite")
    load_csvs(conn, DATA_DIR, "sqlite")
    yield conn
    conn.close()


def read_csv(name: str) -> list[dict]:
    with (DATA_DIR / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
