-- Title: Transactions Below Review Limit
-- Category: Structuring
-- Severity: Medium | The pattern warrants review for control avoidance but can arise from ordinary fixed-price commerce.
-- What it flags: Merchants with a material concentration of approved transaction amounts immediately below an illustrative $100 review limit. Both transaction count and portfolio share must be elevated.
-- Why it matters: Repeated amounts immediately below an internal control can indicate deliberate structuring to avoid manual review, enhanced verification, or other merchant controls. Concentration alone does not prove intent.
-- Logic: Counts approved transactions across the synthetic dataset, then measures records from $99.00 through $99.99. The below-limit share is count-based, not dollar-weighted, and the $100 reference is an illustrative internal review limit rather than a card-network or regulatory rule.
-- Thresholds: Illustrative thresholds are a $100.00 review limit, a $1.00 band immediately below it, at least 250 qualifying transactions, and at least 25% of approved transactions in that band. All thresholds would be tuned to a real portfolio; any external program threshold must be verified against current program rules before use.
-- Likely false positives: A $99.99 product, taxes, shipping logic, promotions, or a subscription price can create legitimate clustering. None of the current decoys is concentrated in the illustrative band, so no decoy-specific exclusion is applied.
-- Next step: Confirm the merchant's product catalog and the control actually in force, sample clustered transactions, look for split purchases or amount changes, contact the merchant if intent remains unclear, and adjust review controls rather than taking action from amount clustering alone.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; below_limit_transactions = approved transactions in the illustrative band; approved_transactions = all approved transactions; below_limit_share = qualifying count divided by approved count; illustrative_review_limit_cents = illustrative limit expressed in cents; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        10000 AS review_limit_cents,
        100 AS review_band_cents,
        250 AS minimum_below_limit_transactions,
        0.25 AS minimum_below_limit_share
),
approved_transaction_counts AS (
    SELECT
        transaction.merchant_id,
        count(*) AS approved_transactions,
        count(*) FILTER (
            WHERE transaction.amount_cents >= parameters.review_limit_cents
                - parameters.review_band_cents
              AND transaction.amount_cents < parameters.review_limit_cents
        ) AS below_limit_transactions
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.status = 'approved'
      AND transaction.occurred_at < parameters.as_of_date
    GROUP BY transaction.merchant_id
),
amount_concentration AS (
    SELECT
        approved_transaction_counts.merchant_id,
        approved_transaction_counts.below_limit_transactions,
        approved_transaction_counts.approved_transactions,
        round(
            approved_transaction_counts.below_limit_transactions::DOUBLE
                / approved_transaction_counts.approved_transactions,
            4
        ) AS below_limit_share
    FROM approved_transaction_counts
)
SELECT
    amount_concentration.merchant_id,
    merchant.merchant_name,
    amount_concentration.below_limit_transactions,
    amount_concentration.approved_transactions,
    amount_concentration.below_limit_share,
    parameters.review_limit_cents AS illustrative_review_limit_cents,
    printf(
        '%d approved transactions between $99.00 and $99.99; %.2f%% of approved activity',
        amount_concentration.below_limit_transactions,
        amount_concentration.below_limit_share * 100
    ) AS reason
FROM amount_concentration
CROSS JOIN parameters
JOIN merchants AS merchant USING (merchant_id)
WHERE amount_concentration.below_limit_transactions
        >= parameters.minimum_below_limit_transactions
  AND amount_concentration.below_limit_share >= parameters.minimum_below_limit_share
ORDER BY amount_concentration.below_limit_transactions DESC, amount_concentration.merchant_id;
