-- Title: Portfolio Merchant Summary
-- Category: Portfolio
-- Severity: Low | This is a review and prioritization view rather than an independent allegation of merchant risk.
-- What it flags: This supporting query does not apply a risk flag. It returns one consolidated row for every merchant so an analyst can compare transaction, refund, and chargeback activity before opening a focused review.
-- Why it matters: A consistent portfolio view helps analysts distinguish isolated signals from broader operating patterns and supports defensible prioritization. It also provides denominators needed to interpret event counts.
-- Logic: Aggregates the full synthetic dataset by merchant, counting transaction attempts by status and summing approved volume, refunds, and chargebacks. Refund and chargeback measures use their own recorded rows and amounts; no ratio or threshold is used to exclude merchants.
-- Thresholds: The illustrative scope includes all merchants and all records before the fixed as-of date, with no minimum activity threshold. A real portfolio would tune date windows, materiality filters, and segmentation to its products and review capacity.
-- Likely false positives: Not applicable because this query does not label merchants as suspicious. M0198, M0199, and M0200 remain visible as legitimate decoys so analysts can compare their context with genuinely planted patterns.
-- Next step: Use the summary to select merchants for a targeted query, validate denominators and materiality, and document why a deeper transaction review is or is not warranted.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; category = synthetic merchant category; total_transactions = all transaction attempts; approved_transactions = approved attempts; declined_transactions = declined attempts; approved_volume_cents = approved transaction amount; refund_count = recorded refunds; refund_amount_cents = recorded refunded amount; chargeback_count = recorded chargebacks; chargeback_amount_cents = recorded chargeback amount; reason = plain-English portfolio summary.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative reporting boundary.
    SELECT TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date
),
transaction_activity AS (
    SELECT
        transaction.merchant_id,
        count(*) AS total_transactions,
        count(*) FILTER (WHERE transaction.status = 'approved') AS approved_transactions,
        count(*) FILTER (WHERE transaction.status = 'declined') AS declined_transactions,
        coalesce(
            sum(transaction.amount_cents) FILTER (WHERE transaction.status = 'approved'),
            0
        ) AS approved_volume_cents
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.occurred_at < parameters.as_of_date
    GROUP BY transaction.merchant_id
),
refund_activity AS (
    SELECT
        refund.merchant_id,
        count(*) AS refund_count,
        sum(refund.amount_cents) AS refund_amount_cents
    FROM refunds AS refund
    CROSS JOIN parameters
    WHERE refund.occurred_at < parameters.as_of_date
    GROUP BY refund.merchant_id
),
chargeback_activity AS (
    SELECT
        chargeback.merchant_id,
        count(*) AS chargeback_count,
        sum(chargeback.amount_cents) AS chargeback_amount_cents
    FROM chargebacks AS chargeback
    CROSS JOIN parameters
    WHERE chargeback.occurred_at < parameters.as_of_date
    GROUP BY chargeback.merchant_id
),
merchant_summary AS (
    SELECT
        merchant.merchant_id,
        merchant.merchant_name,
        merchant.category,
        coalesce(transaction_activity.total_transactions, 0) AS total_transactions,
        coalesce(transaction_activity.approved_transactions, 0) AS approved_transactions,
        coalesce(transaction_activity.declined_transactions, 0) AS declined_transactions,
        coalesce(transaction_activity.approved_volume_cents, 0) AS approved_volume_cents,
        coalesce(refund_activity.refund_count, 0) AS refund_count,
        coalesce(refund_activity.refund_amount_cents, 0) AS refund_amount_cents,
        coalesce(chargeback_activity.chargeback_count, 0) AS chargeback_count,
        coalesce(chargeback_activity.chargeback_amount_cents, 0) AS chargeback_amount_cents
    FROM merchants AS merchant
    LEFT JOIN transaction_activity USING (merchant_id)
    LEFT JOIN refund_activity USING (merchant_id)
    LEFT JOIN chargeback_activity USING (merchant_id)
)
SELECT
    merchant_id,
    merchant_name,
    category,
    total_transactions,
    approved_transactions,
    declined_transactions,
    approved_volume_cents,
    refund_count,
    refund_amount_cents,
    chargeback_count,
    chargeback_amount_cents,
    printf(
        '%d approved transactions totaling $%.2f; %d refunds and %d chargebacks recorded',
        approved_transactions,
        approved_volume_cents / 100.0,
        refund_count,
        chargeback_count
    ) AS reason
FROM merchant_summary
ORDER BY merchant_id;
