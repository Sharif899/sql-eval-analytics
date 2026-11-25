-- name: review_turnaround
-- question: How long does QA review take, per reviewer — and who is the
--   bottleneck? Average and maximum turnaround plus the share of reviews
--   older than 48 hours. (The median and p90 live in
--   queries/postgres_only/median_review_turnaround.sql, because
--   percentile_cont does not exist in SQLite.)
-- dialect: postgres (runs on SQLite via the dialect translation)
WITH timed AS (
    SELECT
        r.reviewer_id AS reviewer_id,
        EXTRACT(EPOCH FROM (r.reviewed_at - a.submitted_at)) / 3600.0 AS hours
    FROM reviews r
    JOIN annotations a
      ON a.annotation_id = r.annotation_id
)
SELECT
    reviewer_id,
    COUNT(*) AS n_reviews,
    ROUND(AVG(hours), 1) AS avg_hours,
    ROUND(MAX(hours), 1) AS max_hours,
    ROUND(100.0 * SUM(CASE WHEN hours > 48 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_over_48h
FROM timed
GROUP BY reviewer_id
ORDER BY avg_hours DESC;
