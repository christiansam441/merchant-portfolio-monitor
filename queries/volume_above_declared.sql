-- Title: Volume Above Declared Level
-- Category: Activity Change
-- Severity: High | Materially exceeding underwritten volume can change loss exposure and indicate an undeclared business shift.
-- What it flags: Merchants whose approved transaction volume during the last 30 days is both materially large and at least three times their declared monthly volume.
-- Why it matters: Volume far above declared activity can indicate inaccurate onboarding, rapid risk-profile change, transaction laundering, or compromised merchant access. Exposure can grow faster than reserves and monitoring assumptions.
-- Logic: Sums approved transaction amounts by merchant during the 30 days before the fixed as-of date. It compares that dollar volume, measured in cents, with the merchant's declared monthly volume; declined and reversed transactions are excluded.
-- Thresholds: Illustrative thresholds are at least $200,000 in approved 30-day volume and at least 3 times declared monthly volume. All thresholds would be tuned to a real portfolio, merchant segment, and expected seasonality.
-- Likely false positives: Seasonal demand, a major promotion, acquisition, or newly signed contract can legitimately exceed forecasts. M0198 is the seasonal-volume decoy; it is excluded because its declared monthly capacity covers the observed spike.
-- Next step: Request recent processing statements and support for the growth event, compare customers and products with the declared business model, review authorization and settlement concentration, update underwriting if legitimate, and consider a reserve or hold if source or purpose cannot be validated.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; approved_transactions = approved transactions in the 30-day window; approved_volume_cents = their total amount in cents; declared_monthly_volume_cents = merchant-declared monthly amount; declared_volume_multiple = observed volume divided by declared volume; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        30 AS lookback_days,
        20000000 AS minimum_approved_volume_cents,
        3.0 AS minimum_declared_volume_multiple
),
recent_approved_volume AS (
    SELECT
        transaction.merchant_id,
        count(*) AS approved_transactions,
        sum(transaction.amount_cents) AS approved_volume_cents
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.status = 'approved'
      AND transaction.occurred_at >= parameters.as_of_date
          - parameters.lookback_days * INTERVAL '1 day'
      AND transaction.occurred_at < parameters.as_of_date
    GROUP BY transaction.merchant_id
),
volume_comparison AS (
    SELECT
        recent_approved_volume.merchant_id,
        recent_approved_volume.approved_transactions,
        recent_approved_volume.approved_volume_cents,
        merchant.declared_monthly_volume_cents,
        round(
            recent_approved_volume.approved_volume_cents::DOUBLE
                / merchant.declared_monthly_volume_cents,
            2
        ) AS declared_volume_multiple
    FROM recent_approved_volume
    JOIN merchants AS merchant USING (merchant_id)
)
SELECT
    volume_comparison.merchant_id,
    merchant.merchant_name,
    volume_comparison.approved_transactions,
    volume_comparison.approved_volume_cents,
    volume_comparison.declared_monthly_volume_cents,
    volume_comparison.declared_volume_multiple,
    printf(
        '$%.2f approved in 30 days, %.2fx the declared monthly volume of $%.2f',
        volume_comparison.approved_volume_cents / 100.0,
        volume_comparison.declared_volume_multiple,
        volume_comparison.declared_monthly_volume_cents / 100.0
    ) AS reason
FROM volume_comparison
CROSS JOIN parameters
JOIN merchants AS merchant USING (merchant_id)
WHERE volume_comparison.approved_volume_cents >= parameters.minimum_approved_volume_cents
  AND volume_comparison.declared_volume_multiple >= parameters.minimum_declared_volume_multiple
ORDER BY volume_comparison.declared_volume_multiple DESC, volume_comparison.merchant_id;
