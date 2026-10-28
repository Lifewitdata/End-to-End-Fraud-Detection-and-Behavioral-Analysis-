-- Executed after the untouched test set has been scored into test_scored.
CREATE OR REPLACE TABLE hourly_monitoring AS
SELECT step, COUNT(*) AS transactions, SUM(isFraud) AS confirmed_fraud,
 SUM(prediction) AS alerts,
 SUM(CASE WHEN prediction=1 AND isFraud=1 THEN 1 ELSE 0 END) AS true_positives,
 SUM(CASE WHEN prediction=1 AND isFraud=0 THEN 1 ELSE 0 END) AS false_positives,
 SUM(CASE WHEN prediction=0 AND isFraud=1 THEN 1 ELSE 0 END) AS false_negatives,
 SUM(CASE WHEN isFraud=1 THEN amount ELSE 0 END) AS fraud_value,
 SUM(CASE WHEN prediction=1 AND isFraud=1 THEN amount ELSE 0 END) AS captured_value
FROM test_scored GROUP BY step ORDER BY step;

CREATE OR REPLACE TABLE recipient_investigation AS
SELECT nameDest, COUNT(*) AS transactions, COUNT(DISTINCT nameOrig) AS distinct_senders,
 SUM(amount) AS transaction_value, SUM(isFraud) AS confirmed_fraud,
 SUM(prediction) AS alerts,
 SUM(CASE WHEN isFraud=1 THEN amount ELSE 0 END) AS fraud_value
FROM test_scored GROUP BY nameDest ORDER BY fraud_value DESC;

-- Rule-event bridge plus registry joins. A transaction may trigger several rules;
-- per-rule counts overlap and must never be summed as unique total alerts.
CREATE OR REPLACE TABLE rule_events AS
SELECT t.row_id, u.rule_id
FROM test_scored t,
UNNEST(string_split(t.triggered_rules, ';')) AS u(rule_id)
WHERE u.rule_id <> '';

CREATE OR REPLACE TABLE rule_performance AS
SELECT r.rule_id, r.description, r.owner, r.version,
 COUNT(t.row_id) AS alerts,
 COALESCE(SUM(t.isFraud), 0) AS true_positives,
 COUNT(t.row_id)-COALESCE(SUM(t.isFraud), 0) AS false_positives,
 COALESCE(SUM(t.isFraud)*1.0/NULLIF(COUNT(t.row_id), 0), 0) AS precision,
 COALESCE(SUM(CASE WHEN t.isFraud=1 THEN t.amount ELSE 0 END), 0) AS captured_value
FROM rule_registry r LEFT JOIN rule_events e ON r.rule_id=e.rule_id
LEFT JOIN test_scored t ON t.row_id=e.row_id
GROUP BY r.rule_id,r.description,r.owner,r.version ORDER BY r.rule_id;
