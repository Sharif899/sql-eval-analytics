-- name: annotator_throughput
-- question: Who is labelling how much, week by week — and who is falling
--   behind? Running totals and a within-week rank make the slow annotator
--   visible without a separate report.
-- dialect: postgres (runs on SQLite via the dialect translation)
WITH weekly AS (
    SELECT
        annotator_id,
        date_trunc('week', submitted_at) AS week_start,
        COUNT(*) AS n_annotations
    FROM annotations
    GROUP BY annotator_id, date_trunc('week', submitted_at)
)
SELECT
    annotator_id,
    week_start,
    n_annotations,
    SUM(n_annotations) OVER (
        PARTITION BY annotator_id
        ORDER BY week_start
    ) AS running_total,
    RANK() OVER (
        PARTITION BY week_start
        ORDER BY n_annotations DESC
    ) AS week_rank
FROM weekly
ORDER BY week_start, week_rank;
