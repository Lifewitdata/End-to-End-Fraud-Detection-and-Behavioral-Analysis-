-- DuckDB. `transactions` is a validated, typed input table with stable row_id.
-- PaySim step has hourly granularity: exclude ALL events in the current step.
-- Current-step event order cannot be inferred from CSV row order.
CREATE OR REPLACE TABLE features AS
WITH history AS (
 SELECT *,
   COUNT(*) OVER sender_window AS sender_count_24h,
   AVG(amount) OVER sender_window AS sender_mean_24h,
   COUNT(*) OVER recipient_window AS recipient_count_24h,
   COUNT(DISTINCT nameOrig) OVER recipient_window AS recipient_senders_24h,
   AVG(amount) OVER recipient_window AS recipient_mean_24h
 FROM transactions
 WINDOW
   sender_window AS (PARTITION BY nameOrig ORDER BY step
                    RANGE BETWEEN 24 PRECEDING AND 1 PRECEDING),
   recipient_window AS (PARTITION BY nameDest ORDER BY step
                       RANGE BETWEEN 24 PRECEDING AND 1 PRECEDING)
)
SELECT *, LN(1 + amount) AS log_amount,
 COALESCE(amount / NULLIF(sender_mean_24h, 0), 1.0) AS sender_amount_ratio,
 COALESCE(amount / NULLIF(recipient_mean_24h, 0), 1.0) AS recipient_amount_ratio
FROM history;
