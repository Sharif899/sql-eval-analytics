"""Query tests: every query's real numbers, cross-checked in Python.

The expected values are computed here from the CSVs with independent
Python logic — not copied from a previous SQL run — so a wrong query fails
instead of agreeing with itself.
"""

from collections import defaultdict
from datetime import datetime

import pytest

from sql_eval_analytics import queries as query_mod
from tests.conftest import read_csv

LABELS = ("correct", "incorrect", "unsure")

# Rounding tolerance note: SQLite ROUND() is half-away-from-zero, Python
# round() is banker's, so the same true value can differ by 0.1 at one
# decimal (or 0.01 at two decimals) when it lands exactly halfway. The
# tolerances below (0.11 / 0.011) cover that and nothing more.
ONE_DP = 0.11
TWO_DP = 0.011


def _monday(date_str: str) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").date()
    return (d - __import__("datetime").timedelta(days=d.weekday())).isoformat()


def _first_annotations():
    """First judgement per (item, annotator), as the agreement queries do."""
    anns = read_csv("annotations.csv")
    first = {}
    for a in sorted(anns, key=lambda r: (r["submitted_at"], int(r["annotation_id"]))):
        first.setdefault((a["item_id"], a["annotator_id"]), a)
    return first


def _pairs():
    items = {r["item_id"]: r for r in read_csv("items.csv")}
    by_item = defaultdict(list)
    for (item, _), a in _first_annotations().items():
        by_item[item].append(a)
    pairs = []
    for item, rows in by_item.items():
        rows.sort(key=lambda r: r["annotator_id"])
        assert len(rows) == 2, f"{item} does not have exactly two annotators"
        pairs.append((items[item]["project"], rows[0]["label"], rows[1]["label"]))
    return pairs


def _kappa(pairs):
    n = len(pairs)
    po = sum(1 for _, a, b in pairs if a == b) / n
    pe = sum(
        (sum(1 for _, a, _ in pairs if a == lab) / n)
        * (sum(1 for _, _, b in pairs if b == lab) / n)
        for lab in LABELS
    )
    return (po - pe) / (1 - pe)


def test_query_registry_lists_ten_queries():
    listed = query_mod.list_queries()
    assert len(listed) == 10
    assert len({q.name for q in listed}) == 10
    assert sum(q.postgres_only for q in listed) == 1
    assert query_mod.get_query("median_review_turnaround").postgres_only
    with pytest.raises(KeyError, match="unknown query"):
        query_mod.get_query("not_a_query")


def test_annotator_agreement_matches_python(db):
    pairs = _pairs()
    rows = {r["project"]: r for r in query_mod.run_query(db, query_mod.get_query("annotator_agreement"), "sqlite")}
    assert rows["ALL"]["n_pairs"] == 60
    assert rows["ALL"]["n_agree"] == 48
    assert rows["ALL"]["agreement_pct"] == 80.0
    assert abs(rows["ALL"]["cohens_kappa"] - _kappa(pairs)) < 0.002
    assert abs(rows["ALL"]["cohens_kappa"] - 0.643) < 0.002
    # Per project, from the same Python pairs.
    for project in ("yoruba-qa", "maths-tutor", "safety-review"):
        sub = [p for p in pairs if p[0] == project]
        assert rows[project]["n_pairs"] == len(sub)
        assert rows[project]["agreement_pct"] == pytest.approx(
            round(100 * sum(1 for _, a, b in sub if a == b) / len(sub), 1), abs=ONE_DP
        )
        assert abs(rows[project]["cohens_kappa"] - _kappa(sub)) < 0.002
    # The ambiguous project really is the worst.
    assert rows["safety-review"]["cohens_kappa"] < rows["maths-tutor"]["cohens_kappa"]
    assert rows["safety-review"]["agreement_pct"] == 75.0
    assert rows["maths-tutor"]["agreement_pct"] == 85.0
    assert rows["maths-tutor"]["cohens_kappa"] == pytest.approx(0.721, abs=0.002)


def test_annotator_throughput(db):
    rows = query_mod.run_query(db, query_mod.get_query("annotator_throughput"), "sqlite")
    assert sum(r["n_annotations"] for r in rows) == 122
    assert len({r["week_start"] for r in rows}) == 7
    # Every week_start is a Monday.
    for r in rows:
        assert datetime.strptime(r["week_start"], "%Y-%m-%d").weekday() == 0
    # Funke (A06) has 16 annotations including her duplicate; her running
    # total ends there. Everyone else ends at 14 or 15.
    last_a06 = [r for r in rows if r["annotator_id"] == "A06"][-1]
    assert last_a06["running_total"] == 16
    assert last_a06["week_start"] == "2026-02-16"


def test_review_turnaround(db):
    rows = {r["reviewer_id"]: r for r in query_mod.run_query(db, query_mod.get_query("review_turnaround"), "sqlite")}
    assert rows["A02"]["avg_hours"] == 116.9
    assert rows["A02"]["pct_over_48h"] == 100.0
    assert rows["A02"]["max_hours"] == 138.0
    assert rows["A01"]["avg_hours"] == 17.3
    assert rows["A01"]["pct_over_48h"] == 0.0
    assert rows["A05"]["avg_hours"] == 17.3
    # Cross-check the average against the raw timestamps.
    anns = {int(a["annotation_id"]): a for a in read_csv("annotations.csv")}
    hours = defaultdict(list)
    for rev in read_csv("reviews.csv"):
        submitted = datetime.strptime(anns[int(rev["annotation_id"])]["submitted_at"], "%Y-%m-%d %H:%M:%S")
        reviewed = datetime.strptime(rev["reviewed_at"], "%Y-%m-%d %H:%M:%S")
        hours[rev["reviewer_id"]].append((reviewed - submitted).total_seconds() / 3600)
    for reviewer, vals in hours.items():
        assert rows[reviewer]["avg_hours"] == pytest.approx(
            round(sum(vals) / len(vals), 1), abs=ONE_DP
        )


def test_quality_reject_rates(db):
    rows = query_mod.run_query(db, query_mod.get_query("quality_reject_rates"), "sqlite")
    by_key = {(r["project"], r["cohort"]): r for r in rows}
    overall = by_key[("ALL", "ALL")]
    assert overall["n_reviewed"] == 116
    assert overall["n_reject"] == 15
    assert overall["reject_pct"] == 12.9
    # The bad batch hit the juniors on maths-tutor hardest.
    assert by_key[("maths-tutor", "junior")]["reject_pct"] == 28.6
    assert by_key[("maths-tutor", "senior")]["reject_pct"] == 0.0
    # Cross-check one cell against the CSVs.
    assert by_key[("yoruba-qa", "senior")]["n_reviewed"] == 15


def test_score_calibration(db):
    rows = query_mod.run_query(db, query_mod.get_query("score_calibration"), "sqlite")
    assert len(rows) == 16  # 2 models x 4 categories x 2 slices
    by_key = {(r["model"], r["category"], r["slice"]): r for r in rows}
    # model-b is miscalibrated on maths and its best scores are instruction.
    assert by_key[("model-b", "maths", "en")]["calibration_gap"] == 0.27
    assert by_key[("model-b", "maths", "en")]["verdict"] == "overconfident"
    assert by_key[("model-b", "maths", "en")]["pass_pct"] == 40.0
    assert by_key[("model-b", "maths", "yo")]["pass_pct"] == 20.0
    assert by_key[("model-b", "instruction_following", "en")]["mean_rubric"] == 5.0
    # Every row re-derived from scores.csv.
    runs = {r["run_id"]: r["model"] for r in read_csv("eval_runs.csv")}
    groups = defaultdict(list)
    for s in read_csv("scores.csv"):
        groups[(runs[s["run_id"]], s["category"], s["slice"])].append(s)
    for key, items in groups.items():
        row = by_key[key]
        mean_rubric = sum(int(s["rubric_score"]) for s in items) / len(items)
        mean_factual = sum(float(s["factual_accuracy"]) for s in items) / len(items)
        assert abs(row["mean_rubric"] - round(mean_rubric, 2)) < TWO_DP
        assert abs(row["mean_factual"] - round(mean_factual, 2)) < TWO_DP
        assert abs(row["calibration_gap"] - round(mean_rubric / 5 - mean_factual, 2)) < TWO_DP
        expected = (
            "overconfident"
            if mean_rubric / 5 - mean_factual > 0.10
            else "underconfident"
            if mean_factual - mean_rubric / 5 > 0.10
            else "calibrated"
        )
        assert row["verdict"] == expected


def test_weekly_trends(db):
    rows = query_mod.run_query(db, query_mod.get_query("weekly_trends"), "sqlite")
    assert sum(r["n_submitted"] for r in rows) == 122
    assert sum(r["n_reviewed"] for r in rows) == 116
    by_week = {r["week_start"]: r for r in rows}
    assert by_week["2026-01-05"]["n_submitted"] == 22
    assert by_week["2026-01-19"]["reject_pct"] == pytest.approx(15.8, abs=ONE_DP)
    # Cross-check against the CSVs.
    ann_weeks = defaultdict(int)
    for a in read_csv("annotations.csv"):
        ann_weeks[_monday(a["submitted_at"])] += 1
    for week, n in ann_weeks.items():
        assert by_week[week]["n_submitted"] == n


def test_duplicate_submissions(db):
    rows = query_mod.run_query(db, query_mod.get_query("duplicate_submissions"), "sqlite")
    assert len(rows) == 2
    by_key = {(r["item_id"], r["annotator_id"]): r for r in rows}
    assert by_key[("itm-003", "A03")]["n_submissions"] == 2
    assert by_key[("itm-003", "A03")]["distinct_labels"] == 1
    assert by_key[("itm-006", "A06")]["n_submissions"] == 2
    assert by_key[("itm-006", "A06")]["distinct_labels"] == 2


def test_reviewer_workload(db):
    rows = query_mod.run_query(db, query_mod.get_query("reviewer_workload"), "sqlite")
    assert all(r["n_unreviewed"] == 6 for r in rows)
    assert all(r["oldest_unreviewed"] == "2026-02-14 02:00:00" for r in rows)
    reviewed = {int(r["annotation_id"]) for r in read_csv("reviews.csv")}
    unreviewed = [a for a in read_csv("annotations.csv") if int(a["annotation_id"]) not in reviewed]
    assert len(unreviewed) == 6
    assert min(a["submitted_at"] for a in unreviewed) == "2026-02-14 02:00:00"


def test_annotator_confidence_vs_accuracy(db):
    rows = query_mod.run_query(db, query_mod.get_query("annotator_confidence_vs_accuracy"), "sqlite")
    by_id = {r["annotator_id"]: r for r in rows}
    # The most overconfident annotator is a junior, as planted.
    assert rows[0]["annotator_id"] == "A06"
    assert rows[0]["overconfidence_gap"] == 0.15
    assert rows[0]["mean_confidence"] == 0.88
    assert rows[0]["agree_pct"] == 73.3
    assert by_id["A03"]["mean_confidence"] == 0.90
    # Cross-check A06's agreement against the paired labels.
    first = _first_annotations()
    by_item = defaultdict(list)
    for (item, annotator), a in first.items():
        by_item[item].append(a)
    agree = defaultdict(lambda: [0, 0])
    for item, items_rows in by_item.items():
        items_rows.sort(key=lambda r: r["annotator_id"])
        a, b = items_rows
        for me, other in ((a, b), (b, a)):
            agree[me["annotator_id"]][1] += 1
            if me["label"] == other["label"]:
                agree[me["annotator_id"]][0] += 1
    for annotator, (n_agree, n) in agree.items():
        assert by_id[annotator]["agree_pct"] == pytest.approx(
            round(100 * n_agree / n, 1), abs=ONE_DP
        )


def test_postgres_only_query_is_skipped_on_sqlite(db):
    query = query_mod.get_query("median_review_turnaround")
    assert query.postgres_only
    with pytest.raises(query_mod.PostgresOnlyError, match="needs PostgreSQL"):
        query_mod.run_query(db, query, "sqlite")
    results = query_mod.run_all(db, "sqlite")
    assert results["median_review_turnaround"]["skipped"].startswith("PostgreSQL-only")
    assert results["median_review_turnaround"]["rows"] == []
    assert len(results) == 10
