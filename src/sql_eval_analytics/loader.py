"""Load the example CSVs into the database.

Rows are inserted in foreign-key order. Annotation ids are supplied in the
CSV (not generated) so reviews can reference them exactly; the loader
inserts them verbatim on both engines. Bad data fails loudly: a missing
file, a missing column, or a constraint violation aborts the load with the
underlying error, rather than silently skipping rows.
"""

from __future__ import annotations

import csv
from pathlib import Path

# (csv file, table, columns, converters)
# Converters take the raw CSV string and return the value to bind, or None
# for an empty cell. Python bools bind as BOOLEAN on PostgreSQL and as 1/0
# on SQLite, which is what both engines expect.
_SPECS = (
    (
        "annotators.csv",
        "annotators",
        ("annotator_id", "name", "cohort", "joined_date", "active"),
        {"active": lambda v: v.strip().lower() == "true"},
    ),
    (
        "items.csv",
        "annotation_items",
        ("item_id", "project", "task_type", "category", "difficulty", "created_at"),
        {},
    ),
    (
        "annotations.csv",
        "annotations",
        ("annotation_id", "item_id", "annotator_id", "label", "confidence", "submitted_at"),
        {"annotation_id": int, "confidence": float},
    ),
    (
        "reviews.csv",
        "reviews",
        ("review_id", "annotation_id", "reviewer_id", "decision", "reviewed_at", "note"),
        {"review_id": int, "annotation_id": int},
    ),
    (
        "eval_runs.csv",
        "eval_runs",
        ("run_id", "model", "dataset_version", "engine", "run_date"),
        {},
    ),
    (
        "scores.csv",
        "scores",
        ("run_id", "item_id", "category", "slice", "rubric_score", "factual_accuracy", "passed"),
        {
            "rubric_score": int,
            "factual_accuracy": float,
            "passed": lambda v: v.strip().lower() == "true",
        },
    ),
)


def _convert(value: str, converters: dict, column: str):
    if value == "" or value is None:
        return None
    converter = converters.get(column)
    return converter(value) if converter is not None else value


def load_csvs(conn, data_dir: str | Path, dialect: str) -> dict[str, int]:
    """Load every CSV in data_dir into the (already created) schema."""
    data_dir = Path(data_dir)
    param_mark = "?" if dialect == "sqlite" else "%s"
    counts: dict[str, int] = {}
    cur = conn.cursor()
    for filename, table, columns, converters in _SPECS:
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"missing data file: {path}")
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in columns if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{filename} is missing columns: {', '.join(missing)}")
            rows = [
                tuple(_convert(row[c], converters, c) for c in columns)
                for row in reader
            ]
        marks = ", ".join(param_mark for _ in columns)
        cur.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({marks})",
            rows,
        )
        counts[table] = len(rows)
    conn.commit()
    return counts
