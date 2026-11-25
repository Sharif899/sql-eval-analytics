-- name: annotator_confidence_vs_accuracy
-- question: Who is overconfident? Mean self-reported confidence next to the
--   annotator's actual agreement with their partner on the same items. A
--   junior who is 0.95 sure and agrees 60% of the time is not confident —
--   they are uncalibrated, and their labels need a second look.
-- dialect: postgres (runs on SQLite via the dialect translation)
WITH deduped AS (
    SELECT
        item_id,
        annotator_id,
        label,
        confidence,
        ROW_NUMBER() OVER (
            PARTITION BY item_id, annotator_id
            ORDER BY submitted_at, annotation_id
        ) AS rn
    FROM annotations
),
firsts AS (
    SELECT item_id, annotator_id, label, confidence
    FROM deduped
    WHERE rn = 1
),
pairs AS (
    SELECT
        a1.annotator_id AS annotator_a,
        a2.annotator_id AS annotator_b,
        a1.label AS label_a,
        a2.label AS label_b
    FROM firsts a1
    JOIN firsts a2
      ON a2.item_id = a1.item_id
     AND a2.annotator_id > a1.annotator_id
),
pair_sides AS (
    SELECT annotator_a AS annotator_id, label_a, label_b FROM pairs
    UNION ALL
    SELECT annotator_b AS annotator_id, label_b, label_a FROM pairs
),
per_annotator AS (
    SELECT
        annotator_id,
        COUNT(*) AS n_annotations,
        ROUND(AVG(confidence), 2) AS mean_confidence
    FROM firsts
    GROUP BY annotator_id
),
agreement AS (
    SELECT
        annotator_id,
        COUNT(*) AS n_paired,
        ROUND(100.0 * SUM(CASE WHEN label_a = label_b THEN 1 ELSE 0 END) / COUNT(*), 1) AS agree_pct
    FROM pair_sides
    GROUP BY annotator_id
)
SELECT
    p.annotator_id AS annotator_id,
    an.cohort AS cohort,
    p.n_annotations AS n_annotations,
    p.mean_confidence AS mean_confidence,
    a.n_paired AS n_paired,
    a.agree_pct AS agree_pct,
    ROUND(p.mean_confidence - a.agree_pct / 100.0, 2) AS overconfidence_gap
FROM per_annotator p
JOIN annotators an
  ON an.annotator_id = p.annotator_id
JOIN agreement a
  ON a.annotator_id = p.annotator_id
ORDER BY overconfidence_gap DESC;
