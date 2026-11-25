-- name: annotator_agreement
-- question: How much do annotators agree, per project — and is that agreement
--   real, or just the base rate? (Cohen's kappa, not raw agreement.)
-- dialect: postgres (runs on SQLite via the dialect translation)
--
-- Duplicate submissions are de-duplicated first: only the first judgement
-- per (item, annotator) counts towards agreement. The duplicates themselves
-- are the subject of duplicate_submissions.sql.
WITH deduped AS (
    SELECT
        item_id,
        annotator_id,
        label,
        ROW_NUMBER() OVER (
            PARTITION BY item_id, annotator_id
            ORDER BY submitted_at, annotation_id
        ) AS rn
    FROM annotations
),
firsts AS (
    SELECT item_id, annotator_id, label
    FROM deduped
    WHERE rn = 1
),
pairs AS (
    SELECT
        a1.item_id AS item_id,
        i.project AS project,
        a1.label AS label_a,
        a2.label AS label_b
    FROM firsts a1
    JOIN firsts a2
      ON a2.item_id = a1.item_id
     AND a2.annotator_id > a1.annotator_id
    JOIN annotation_items i
      ON i.item_id = a1.item_id
),
stats AS (
    SELECT
        project,
        COUNT(*) AS n_pairs,
        SUM(CASE WHEN label_a = label_b THEN 1 ELSE 0 END) AS n_agree,
        SUM(CASE WHEN label_a = 'correct' THEN 1 ELSE 0 END) AS a_correct,
        SUM(CASE WHEN label_a = 'incorrect' THEN 1 ELSE 0 END) AS a_incorrect,
        SUM(CASE WHEN label_a = 'unsure' THEN 1 ELSE 0 END) AS a_unsure,
        SUM(CASE WHEN label_b = 'correct' THEN 1 ELSE 0 END) AS b_correct,
        SUM(CASE WHEN label_b = 'incorrect' THEN 1 ELSE 0 END) AS b_incorrect,
        SUM(CASE WHEN label_b = 'unsure' THEN 1 ELSE 0 END) AS b_unsure
    FROM pairs
    GROUP BY project
),
rates AS (
    SELECT
        project,
        n_pairs,
        n_agree,
        1.0 * n_agree / n_pairs AS po,
        (1.0 * a_correct * b_correct
         + 1.0 * a_incorrect * b_incorrect
         + 1.0 * a_unsure * b_unsure) / (n_pairs * n_pairs) AS pe
    FROM stats
),
overall AS (
    SELECT
        'ALL' AS project,
        COUNT(*) AS n_pairs,
        SUM(CASE WHEN label_a = label_b THEN 1 ELSE 0 END) AS n_agree,
        1.0 * SUM(CASE WHEN label_a = label_b THEN 1 ELSE 0 END) / COUNT(*) AS po,
        (1.0 * SUM(CASE WHEN label_a = 'correct' THEN 1 ELSE 0 END)
               * SUM(CASE WHEN label_b = 'correct' THEN 1 ELSE 0 END)
         + 1.0 * SUM(CASE WHEN label_a = 'incorrect' THEN 1 ELSE 0 END)
               * SUM(CASE WHEN label_b = 'incorrect' THEN 1 ELSE 0 END)
         + 1.0 * SUM(CASE WHEN label_a = 'unsure' THEN 1 ELSE 0 END)
               * SUM(CASE WHEN label_b = 'unsure' THEN 1 ELSE 0 END))
        / (COUNT(*) * COUNT(*)) AS pe
    FROM pairs
)
SELECT
    project,
    n_pairs,
    n_agree,
    ROUND(100.0 * po, 1) AS agreement_pct,
    ROUND((po - pe) / NULLIF(1 - pe, 0), 3) AS cohens_kappa
FROM (
    SELECT project, n_pairs, n_agree, po, pe FROM rates
    UNION ALL
    SELECT project, n_pairs, n_agree, po, pe FROM overall
) combined
ORDER BY project;
