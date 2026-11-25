-- name: reviewer_workload
-- question: Who is carrying the review queue, and how old is what is still
--   sitting in it? Weekly reviews per reviewer, with the current backlog
--   (annotations with no review row) and its oldest item attached to every
--   row, so the queue age is visible next to the throughput.
-- dialect: postgres (runs on SQLite via the dialect translation)
WITH weekly AS (
    SELECT
        r.reviewer_id AS reviewer_id,
        date_trunc('week', r.reviewed_at) AS week_start,
        COUNT(*) AS n_reviews
    FROM reviews r
    GROUP BY r.reviewer_id, date_trunc('week', r.reviewed_at)
),
backlog AS (
    SELECT
        COUNT(*) AS n_unreviewed,
        MIN(a.submitted_at) AS oldest_unreviewed
    FROM annotations a
    LEFT JOIN reviews r
      ON r.annotation_id = a.annotation_id
    WHERE r.review_id IS NULL
)
SELECT
    w.reviewer_id AS reviewer_id,
    w.week_start AS week_start,
    w.n_reviews AS n_reviews,
    b.n_unreviewed AS n_unreviewed,
    b.oldest_unreviewed AS oldest_unreviewed
FROM weekly w
CROSS JOIN backlog b
ORDER BY w.week_start, w.reviewer_id;
