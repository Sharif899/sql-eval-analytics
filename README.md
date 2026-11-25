# sql-eval-analytics

SQL analytics for AI evaluation operations. The schema and queries a QA
lead actually runs: how much do annotators agree, who is slow, where is
quality breaking down, and is a model's confidence worth anything.

This is the SQL side of the evaluation work I do — the same kind of
analysis behind the Databricks evaluation pipelines (75,000+ test cases)
and the PostgreSQL-backed KYC systems at Seamfix. No models are trained
here. The point is the data underneath the models: the annotators, the
reviews, and the scores.

## What it answers

Ten queries, each one a question a QA lead asks out loud:

| Query | Question |
| --- | --- |
| `annotator_agreement` | How much do annotators agree, per project — and is that agreement real, or just the base rate? (Cohen's kappa) |
| `annotator_throughput` | Who is submitting how much, week by week — and who is falling behind? |
| `review_turnaround` | How long does QA review take, per reviewer — and who is the bottleneck? |
| `quality_reject_rates` | Where is quality breaking down — which project, which annotator cohort? |
| `score_calibration` | Does a model's confidence match its accuracy, by category and language slice? |
| `weekly_trends` | Is the operation getting better or worse, week by week? |
| `duplicate_submissions` | Who submitted the same item twice, and did they change their answer? |
| `reviewer_workload` | Who is carrying the review queue, and how old is what is still sitting in it? |
| `annotator_confidence_vs_accuracy` | Who is overconfident — high self-reported confidence, low agreement? |
| `median_review_turnaround` | Median and p90 review turnaround per reviewer. **PostgreSQL-only** (uses `percentile_cont`). |

The SQL is PostgreSQL-first: CTEs, window functions, conditional
aggregation, `date_trunc`. Nine of the ten queries also run on SQLite —
the local engine — through a small translation layer
(`src/sql_eval_analytics/dialect.py`) that rewrites `SERIAL`,
`TIMESTAMPTZ`, `date_trunc('week')` and `EXTRACT(EPOCH FROM …)` into
their SQLite equivalents. The tenth uses `percentile_cont`, which has no
SQLite equivalent, so it is flagged `postgres-only` and skipped (loudly)
on SQLite instead of being silently faked.

## What the example data says

The repo ships with synthetic example data (`data/examples/`, 428 rows:
8 annotators, 60 items, 122 annotations, 116 reviews, 2 model runs,
120 scores). The data is deliberately flawed — every flaw is documented
in `data/examples/README.md` — because clean data proves nothing. Run it:

```bash
pip install -e .
sqleval load --data data/examples --db eval.db
sqleval report --db eval.db
```

Real output from that run:

- **Agreement:** 80.0% overall, Cohen's kappa **0.643**. Safety-review is
  the problem project at 75.0% (κ 0.502); maths-tutor is best at 85.0%
  (κ 0.721). The safety guidelines need rewriting, not the annotators.
- **Turnaround:** one reviewer averages **116.9 hours** per review with
  **100%** of reviews over 48 hours; the other two average **17.3 hours**
  with 0% over 48 hours. That is a single-person bottleneck, not a
  process problem.
- **Rejects:** 12.9% overall (15 of 116). Maths-tutor juniors are rejected
  at **28.6%** against 0.0% for maths-tutor seniors — a bad batch hit the
  juniors hardest.
- **Calibration:** model-b scores itself 3.4/5 on maths (English) while
  getting 41% of the facts right — calibration gap 0.27, pass rate 40%.
  Its best rubric scores are on instruction following (5.0/5) — the one
  category where it beats model-a on rubric — but its factual accuracy
  there (0.69–0.73) still lags far behind its own rubric (gap 0.19–0.31).
  model-a is calibrated on maths in English (4.6/5, 82% factual, gap
  0.10, 100% pass).
- **Overconfidence:** the most overconfident annotator is a junior at
  0.88 mean confidence against 73.3% agreement (gap +0.15). The most
  accurate annotator is a senior at 0.79 confidence and 93.3% agreement
  (gap −0.14) — underconfident, not overconfident.
- **Duplicates:** two found — one annotator re-submitted the same label,
  one changed theirs.
- **Backlog:** 6 annotations unreviewed; the oldest has been waiting
  since 2026-02-14.

## Running it against real PostgreSQL

```bash
export DATABASE_URL="postgresql://user:password@host:5432/dbname"
sqleval load --postgres --data data/examples
sqleval report --postgres
```

The connection string comes from the `DATABASE_URL` environment variable
only. Never put credentials in a file, a command line, or a commit —
`sqleval` reads no config file and accepts no password argument, on
purpose. If `DATABASE_URL` is not set, `--postgres` fails with an error
instead of guessing.

The schema is `src/sql_eval_analytics/schema.sql`. Point it at a real
operations database by exporting the same tables from your own system
into the CSV format in `data/examples/` and running `sqleval load` — the
loader expects the same columns, and fails loudly on a missing file,
a missing column, or a foreign-key violation.

## What it does not do

- **SQLite is the local engine, not the target.** Tests and CI run on
  SQLite so they work anywhere without a server. The SQL is written for
  PostgreSQL and the translation layer is explicit about what it rewrites.
  The one query that cannot be translated is flagged and skipped, not
  approximated.
- **The example data is small and synthetic.** 428 rows is enough to
  exercise every query and expose every planted flaw; it is not a
  performance benchmark. Nothing here is tuned for scale, and no query
  has been run against a production-sized database.
- **No psycopg at runtime unless you ask for it.** The base install is
  Python stdlib only. PostgreSQL support is an optional extra
  (`pip install -e ".[postgres]"`) so the package stays installable
  anywhere.
- **Percentages are rounded the way the database rounds them.**
  SQLite `ROUND()` is half-away-from-zero; Python `round()` is banker's.
  A value that lands exactly halfway can differ by 0.1 between the two.
  The tests account for this explicitly.

## Layout

```
src/sql_eval_analytics/
  schema.sql          PostgreSQL-first DDL (annotators, items, annotations,
                      reviews, eval runs, scores)
  queries/            one .sql file per question, with a -- name: / -- question:
                      header the registry reads
  queries/postgres_only/
                      queries that need PostgreSQL (percentile_cont)
  dialect.py          PostgreSQL -> SQLite translation, with a hard error
                      on anything it cannot translate
  schema.py           create/drop schema, SQLite and PostgreSQL connections
  loader.py           CSV -> database, in foreign-key order
  queries.py          query registry, runner, PostgreSQL-only guard
  report.py           text and JSON report renderers
  cli.py              sqleval load | query | report | list
data/examples/        synthetic data (428 rows) + README documenting
                      every deliberate flaw
tests/                pytest: schema, dialect, every query's real numbers
                      cross-checked in Python, CLI end-to-end
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[postgres]" pytest
python -m pytest -q
```

34 tests, 0 failures. Every query test asserts real values computed
independently in Python from the CSVs — not row counts, and not numbers
copied from a previous SQL run.

## Licence

MIT.
