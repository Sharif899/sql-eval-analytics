-- name: duplicate_submissions
-- question: Did anyone submit the same item twice? A duplicate is usually a
--   retried request or a double-click, and if it is counted twice the
--   throughput and agreement numbers are both wrong. This is the check the
--   other queries assume has already been run.
-- dialect: postgres (runs on SQLite via the dialect translation)
SELECT
    a.item_id AS item_id,
    a.annotator_id AS annotator_id,
    COUNT(*) AS n_submissions,
    MIN(a.submitted_at) AS first_submitted,
    MAX(a.submitted_at) AS last_submitted,
    COUNT(DISTINCT a.label) AS distinct_labels
FROM annotations a
GROUP BY a.item_id, a.annotator_id
HAVING COUNT(*) > 1
ORDER BY n_submissions DESC, a.item_id;
