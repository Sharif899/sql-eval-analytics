-- name: median_review_turnaround
-- question: What is the median and p90 review turnaround per reviewer?
--   Same question as review_turnaround.sql, answered properly.
-- dialect: postgres-only (percentile_cont does not exist in SQLite)
--
-- This file is NOT run on SQLite. The CLI lists it and skips it with a
-- note on the local engine; on PostgreSQL it runs as written. The portable
-- version of the same question is review_turnaround.sql (average, maximum,
-- and share over 48 hours), which runs on both engines.
SELECT
    r.reviewer_id AS reviewer_id,
    COUNT(*) AS n_reviews,
    ROUND(
        percentile_cont(0.5) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (r.reviewed_at - a.submitted_at)) / 3600.0
        ), 1
    ) AS median_hours,
    ROUND(
        percentile_cont(0.9) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (r.reviewed_at - a.submitted_at)) / 3600.0
        ), 1
    ) AS p90_hours
FROM reviews r
JOIN annotations a
  ON a.annotation_id = r.annotation_id
GROUP BY r.reviewer_id
ORDER BY median_hours DESC;
