-- name: weekly_trends
-- question: Is the operation getting better or worse, week by week?
--   Volume submitted, volume reviewed, and the reject rate, on the same
--   Monday-start week both dialects agree on.
-- dialect: postgres (runs on SQLite via the dialect translation)
WITH weekly_ann AS (
    SELECT
        date_trunc('week', submitted_at) AS week_start,
        COUNT(*) AS n_submitted
    FROM annotations
    GROUP BY date_trunc('week', submitted_at)
),
weekly_rev AS (
    SELECT
        date_trunc('week', r.reviewed_at) AS week_start,
        COUNT(*) AS n_reviewed,
        SUM(CASE WHEN r.decision = 'reject' THEN 1 ELSE 0 END) AS n_reject
    FROM reviews r
    GROUP BY date_trunc('week', r.reviewed_at)
)
SELECT
    w.week_start AS week_start,
    w.n_submitted AS n_submitted,
    COALESCE(r.n_reviewed, 0) AS n_reviewed,
    COALESCE(ROUND(100.0 * r.n_reject / NULLIF(r.n_reviewed, 0), 1), 0.0) AS reject_pct
FROM weekly_ann w
LEFT JOIN weekly_rev r
  ON r.week_start = w.week_start
ORDER BY w.week_start;
