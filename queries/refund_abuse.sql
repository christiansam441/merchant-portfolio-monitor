-- Title: Elevated Refund Activity
-- Category: Refunds
-- Severity: High | Sustained refund misuse can cause direct loss, conceal transaction laundering, and undermine settlement controls.
-- What it flags: Merchants with both a high count and high rate of non-cancellation refunds across the 180-day dataset. Documented event-cancellation refunds are measured but excluded from the flag calculation.
-- Why it matters: Excessive refunds can indicate merchant abuse, transaction laundering, fulfillment problems, or misuse of refund capabilities. The combination of count and rate helps distinguish material exposure from isolated customer service events.
-- Logic: Counts refund records by refund occurrence date and excludes rows whose reason is event_cancelled. The count-based refund rate is reviewable refund records divided by all approved transaction records in the synthetic 180-day dataset; the displayed refund amount is supplementary and not used in the threshold.
-- Thresholds: Illustrative thresholds are at least 100 reviewable refunds and a reviewable-refund count equal to at least 15% of approved transactions, using refunds recorded from 2026-03-28 through the as-of date. All thresholds would be tuned to a real portfolio; any card-network or regulatory threshold must be verified against current program rules before use.
-- Likely false positives: Recalls, service outages, generous return programs, or mass event cancellations can elevate legitimate refunds. M0199 is the event-cancellation decoy; its event_cancelled refunds are reported separately but excluded from reviewable refunds, so M0199 does not trigger this query.
-- Next step: Review refund reasons and transaction samples, trace settlement destinations, assess customer and card concentration, request refund policies and supporting event records, contact the merchant, and restrict refund permissions or apply a hold if misuse is substantiated.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; reviewable_refunds = non-cancellation refund count; excluded_event_cancellation_refunds = event-cancellation refunds excluded from the flag; reviewable_refund_amount_cents = total cents refunded for reviewable records; approved_transactions = approved transaction count used as denominator; refund_rate = reviewable refunds divided by approved transactions; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-03-28 00:00:00+00' AS review_start_date,
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        100 AS minimum_reviewable_refunds,
        0.15 AS minimum_refund_rate,
        'event_cancelled' AS excluded_refund_reason
),
approved_transaction_counts AS (
    SELECT
        transaction.merchant_id,
        count(*) AS approved_transactions
    FROM transactions AS transaction
    WHERE transaction.status = 'approved'
    GROUP BY transaction.merchant_id
),
refund_activity AS (
    SELECT
        refund.merchant_id,
        count(*) FILTER (
            WHERE refund.reason <> parameters.excluded_refund_reason
        ) AS reviewable_refunds,
        count(*) FILTER (
            WHERE refund.reason = parameters.excluded_refund_reason
        ) AS excluded_event_cancellation_refunds,
        sum(refund.amount_cents) FILTER (
            WHERE refund.reason <> parameters.excluded_refund_reason
        ) AS reviewable_refund_amount_cents
    FROM refunds AS refund
    CROSS JOIN parameters
    WHERE refund.occurred_at >= parameters.review_start_date
      AND refund.occurred_at < parameters.as_of_date
    GROUP BY refund.merchant_id
),
refund_metrics AS (
    SELECT
        refund_activity.merchant_id,
        refund_activity.reviewable_refunds,
        refund_activity.excluded_event_cancellation_refunds,
        refund_activity.reviewable_refund_amount_cents,
        approved_transaction_counts.approved_transactions,
        round(
            refund_activity.reviewable_refunds::DOUBLE
                / nullif(approved_transaction_counts.approved_transactions, 0),
            4
        ) AS refund_rate
    FROM refund_activity
    JOIN approved_transaction_counts USING (merchant_id)
)
SELECT
    refund_metrics.merchant_id,
    merchant.merchant_name,
    refund_metrics.reviewable_refunds,
    refund_metrics.excluded_event_cancellation_refunds,
    refund_metrics.reviewable_refund_amount_cents,
    refund_metrics.approved_transactions,
    refund_metrics.refund_rate,
    printf(
        '%d reviewable refunds, %.2f%% of approved transactions; %d event-cancellation refunds excluded',
        refund_metrics.reviewable_refunds,
        refund_metrics.refund_rate * 100,
        refund_metrics.excluded_event_cancellation_refunds
    ) AS reason
FROM refund_metrics
CROSS JOIN parameters
JOIN merchants AS merchant USING (merchant_id)
WHERE refund_metrics.reviewable_refunds >= parameters.minimum_reviewable_refunds
  AND refund_metrics.refund_rate >= parameters.minimum_refund_rate
ORDER BY refund_metrics.refund_rate DESC, refund_metrics.merchant_id;
