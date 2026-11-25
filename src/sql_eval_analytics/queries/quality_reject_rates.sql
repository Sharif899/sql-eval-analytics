-- name: quality_reject_rates
-- question: Where is quality breaking down — which project, and which
--   annotator cohort? Reject rate with the full accept / reject /
--   needs-info breakdown, so a high reject rate cannot hide a flood of
--   needs_info.
-- dialect: postgres (runs on SQLite via the dialect translation)
WITH joined AS (
    SELECT
        i.project AS project,
        an.cohort AS cohort,
        r.decision AS decision
    FROM reviews r
    JOIN annotations a
      ON a.annotation_id = r.annotation_id
    JOIN annotation_items i
      ON i.item_id = a.item_id
    JOIN annotators an
      ON an.annotator_id = a.annotator_id
),
grouped AS (
    SELECT
        project,
        cohort,
        COUNT(*) AS n_reviewed,
        SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) AS n_accept,
        SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) AS n_reject,
        SUM(CASE WHEN decision = 'needs_info' THEN 1 ELSE 0 END) AS n_needs_info,
        ROUND(100.0 * SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) / COUNT(*), 1) AS reject_pct
    FROM joined
    GROUP BY project, cohort
),
overall AS (
    SELECT
        'ALL' AS project,
        'ALL' AS cohort,
        COUNT(*) AS n_reviewed,
        SUM(CASE WHEN decision = 'accept' THEN 1 ELSE 0 END) AS n_accept,
        SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) AS n_reject,
        SUM(CASE WHEN decision = 'needs_info' THEN 1 ELSE 0 END) AS n_needs_info,
        ROUND(100.0 * SUM(CASE WHEN decision = 'reject' THEN 1 ELSE 0 END) / COUNT(*), 1) AS reject_pct
    FROM joined
)
SELECT * FROM grouped
UNION ALL
SELECT * FROM overall
ORDER BY project, cohort;
