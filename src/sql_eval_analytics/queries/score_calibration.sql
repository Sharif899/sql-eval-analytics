-- name: score_calibration
-- question: Does a model's confidence match its accuracy? For every
--   (model, category, slice): mean rubric score against mean factual
--   accuracy, the gap between them, and a verdict. A model that scores
--   itself 4.5/5 while getting 40% of the facts right is miscalibrated,
--   and that is a finding about the model, not the data.
-- dialect: postgres (runs on SQLite via the dialect translation)
SELECT
    er.model AS model,
    s.category AS category,
    s.slice AS slice,
    COUNT(*) AS n,
    ROUND(AVG(s.rubric_score), 2) AS mean_rubric,
    ROUND(AVG(s.factual_accuracy), 2) AS mean_factual,
    ROUND(AVG(s.rubric_score) / 5.0 - AVG(s.factual_accuracy), 2) AS calibration_gap,
    CASE
        WHEN AVG(s.rubric_score) / 5.0 - AVG(s.factual_accuracy) > 0.10 THEN 'overconfident'
        WHEN AVG(s.factual_accuracy) - AVG(s.rubric_score) / 5.0 > 0.10 THEN 'underconfident'
        ELSE 'calibrated'
    END AS verdict,
    ROUND(100.0 * SUM(CASE WHEN s.passed THEN 1 ELSE 0 END) / COUNT(*), 1) AS pass_pct
FROM scores s
JOIN eval_runs er
  ON er.run_id = s.run_id
GROUP BY er.model, s.category, s.slice
ORDER BY er.model, s.category, s.slice;
