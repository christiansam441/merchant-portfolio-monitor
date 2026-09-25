-- Title: Chargeback Volume Spike
-- Category: Disputes
-- Severity: High | A concentrated dispute increase can create immediate loss, reserve, and merchant-control exposure.
-- What it flags: Merchants with a sharp increase in newly recorded chargebacks during the last seven days. It requires both meaningful case volume and acceleration from the preceding comparison period.
-- Why it matters: A sudden dispute increase can indicate fraud, fulfillment failure, misleading sales practices, or deteriorating merchant controls. Early review can limit additional loss while the underlying cause is established.
-- Logic: Counts chargeback records by chargeback occurrence date, not sale date, and compares the most recent 7 days with the preceding 30 days. The displayed chargeback rate is count-based: recent chargeback records divided by approved transactions occurring in the same recent 7-day window; it is not dollar-weighted.
-- Thresholds: Illustrative thresholds are at least 20 recent chargebacks and at least 3 times the prior-period count, using a 7-day recent window and 30-day comparison window. All thresholds would be tuned to a real portfolio; any card-network program threshold must be verified against current program rules before use.
-- Likely false positives: Delayed issuer reporting, a product recall, a shipping disruption, or a legitimate batch of disputes can create a short spike. None of the current decoys has a comparable chargeback pattern, so no decoy-specific exclusion is applied.
-- Next step: Review dispute reason and transaction samples, compare sale and fulfillment dates, request recent processing statements and fulfillment evidence, contact the merchant for an explanation, and consider a proportionate reserve or hold if loss is continuing.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; recent_chargebacks = chargebacks recorded in the recent window; prior_chargebacks = chargebacks recorded in the comparison window; recent_approved_transactions = approved sales in the recent window; recent_chargeback_rate = recent chargeback count divided by recent approved transaction count; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        7 AS recent_window_days,
        30 AS comparison_window_days,
        20 AS minimum_recent_chargebacks,
        3.0 AS minimum_count_multiple
),
chargeback_counts AS (
    SELECT
        merchant.merchant_id,
        merchant.merchant_name,
        count(chargeback.chargeback_id) FILTER (
            WHERE chargeback.occurred_at >= parameters.as_of_date
                - parameters.recent_window_days * INTERVAL '1 day'
              AND chargeback.occurred_at < parameters.as_of_date
        ) AS recent_chargebacks,
        count(chargeback.chargeback_id) FILTER (
            WHERE chargeback.occurred_at >= parameters.as_of_date
                - (parameters.recent_window_days + parameters.comparison_window_days) * INTERVAL '1 day'
              AND chargeback.occurred_at < parameters.as_of_date
                - parameters.recent_window_days * INTERVAL '1 day'
        ) AS prior_chargebacks,
        parameters.minimum_recent_chargebacks,
        parameters.minimum_count_multiple
    FROM merchants AS merchant
    CROSS JOIN parameters
    LEFT JOIN chargebacks AS chargeback
        ON merchant.merchant_id = chargeback.merchant_id
    GROUP BY
        merchant.merchant_id,
        merchant.merchant_name,
        parameters.minimum_recent_chargebacks,
        parameters.minimum_count_multiple
),
recent_approved_sales AS (
    SELECT
        transaction.merchant_id,
        count(*) AS recent_approved_transactions
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.status = 'approved'
      AND transaction.occurred_at >= parameters.as_of_date
          - parameters.recent_window_days * INTERVAL '1 day'
      AND transaction.occurred_at < parameters.as_of_date
    GROUP BY transaction.merchant_id
),
merchant_metrics AS (
    SELECT
        chargeback_counts.merchant_id,
        chargeback_counts.merchant_name,
        chargeback_counts.recent_chargebacks,
        chargeback_counts.prior_chargebacks,
        coalesce(recent_approved_sales.recent_approved_transactions, 0)
            AS recent_approved_transactions,
        round(
            chargeback_counts.recent_chargebacks::DOUBLE
                / nullif(recent_approved_sales.recent_approved_transactions, 0),
            4
        ) AS recent_chargeback_rate
    FROM chargeback_counts
    LEFT JOIN recent_approved_sales USING (merchant_id)
    WHERE chargeback_counts.recent_chargebacks
            >= chargeback_counts.minimum_recent_chargebacks
      AND chargeback_counts.recent_chargebacks >= greatest(
            chargeback_counts.prior_chargebacks * chargeback_counts.minimum_count_multiple,
            chargeback_counts.minimum_recent_chargebacks
      )
)
SELECT
    merchant_id,
    merchant_name,
    recent_chargebacks,
    prior_chargebacks,
    recent_approved_transactions,
    recent_chargeback_rate,
    printf(
        '%d chargebacks in 7 days vs %d in the prior 30 days; %.2f%% of recent approved transactions',
        recent_chargebacks,
        prior_chargebacks,
        recent_chargeback_rate * 100
    ) AS reason
FROM merchant_metrics
ORDER BY recent_chargebacks DESC, merchant_id;
