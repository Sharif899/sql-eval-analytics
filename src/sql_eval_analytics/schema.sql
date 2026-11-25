-- sql-eval-analytics — schema
--
-- PostgreSQL-first DDL for AI evaluation operations data: who labelled what,
-- what QA decided about it, and how models scored. Load it on PostgreSQL
-- with psql:
--
--   psql "$DATABASE_URL" -f schema.sql
--
-- The local engine is SQLite (see src/sql_eval_analytics/dialect.py for the
-- small, documented translation applied there). The translation is
-- mechanical — SERIAL and TIMESTAMPTZ only — so this file is the canonical
-- schema and the SQLite copy is never edited by hand.
--
-- Timestamps are stored as ISO-8601 text ('YYYY-MM-DD HH:MM:SS'). PostgreSQL
-- parses that into TIMESTAMPTZ; SQLite's date functions accept the same
-- strings, which is what makes the queries portable.

CREATE TABLE IF NOT EXISTS annotators (
    annotator_id TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    cohort       TEXT NOT NULL CHECK (cohort IN ('junior', 'mid', 'senior')),
    joined_date  DATE NOT NULL,
    active       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS annotation_items (
    item_id     TEXT PRIMARY KEY,
    project     TEXT NOT NULL,
    task_type   TEXT NOT NULL,
    category    TEXT NOT NULL,
    difficulty  TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    created_at  TIMESTAMPTZ NOT NULL
);

-- One row per annotator's judgement of one item. Two annotators per item is
-- the norm, which is what makes agreement measurable. Deliberate duplicates
-- (same annotator, same item, twice) are allowed here on purpose: finding
-- them is one of the queries.
CREATE TABLE IF NOT EXISTS annotations (
    annotation_id SERIAL PRIMARY KEY,
    item_id       TEXT NOT NULL REFERENCES annotation_items (item_id),
    annotator_id  TEXT NOT NULL REFERENCES annotators (annotator_id),
    label         TEXT NOT NULL CHECK (label IN ('correct', 'incorrect', 'unsure')),
    confidence    NUMERIC(3, 2) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    submitted_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotations_item
    ON annotations (item_id);
CREATE INDEX IF NOT EXISTS idx_annotations_annotator
    ON annotations (annotator_id);
CREATE INDEX IF NOT EXISTS idx_annotations_submitted
    ON annotations (submitted_at);

-- QA review of one annotation. An annotation with no review row is still
-- sitting in the queue; the workload query counts those.
CREATE TABLE IF NOT EXISTS reviews (
    review_id     SERIAL PRIMARY KEY,
    annotation_id INTEGER NOT NULL REFERENCES annotations (annotation_id),
    reviewer_id   TEXT NOT NULL REFERENCES annotators (annotator_id),
    decision      TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'needs_info')),
    reviewed_at   TIMESTAMPTZ NOT NULL,
    note          TEXT
);

CREATE INDEX IF NOT EXISTS idx_reviews_annotation
    ON reviews (annotation_id);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer
    ON reviews (reviewer_id);

-- One scored run of one model over a dataset version.
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id          TEXT PRIMARY KEY,
    model           TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    engine          TEXT NOT NULL CHECK (engine IN ('local', 'spark')),
    run_date        DATE NOT NULL
);

-- One scored item inside a run. rubric_score is the 1-5 rubric mean for the
-- item; factual_accuracy is the share of its claims supported by the
-- reference; passed is rubric_score >= 4. slice is the data slice the item
-- belongs to (language or region), which is what calibration is measured on.
CREATE TABLE IF NOT EXISTS scores (
    score_id         SERIAL PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES eval_runs (run_id),
    item_id          TEXT NOT NULL REFERENCES annotation_items (item_id),
    category         TEXT NOT NULL,
    slice            TEXT NOT NULL,
    rubric_score     INTEGER NOT NULL CHECK (rubric_score BETWEEN 1 AND 5),
    factual_accuracy NUMERIC(3, 2) NOT NULL CHECK (factual_accuracy >= 0 AND factual_accuracy <= 1),
    passed           BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scores_run
    ON scores (run_id);
CREATE INDEX IF NOT EXISTS idx_scores_category
    ON scores (category, slice);
