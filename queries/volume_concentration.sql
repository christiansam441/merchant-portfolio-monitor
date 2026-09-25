-- Title: Merchant Volume Concentration
-- Category: Portfolio
-- Severity: Low | Concentration is a portfolio exposure measure, not evidence that an individual merchant is acting improperly.
-- What it flags: The ten merchants contributing the most approved transaction volume during the last 30 days. It shows individual and cumulative portfolio shares for exposure review.
-- Why it matters: A portfolio concentrated in a small number of merchants can amplify credit, fraud, operational, and settlement losses if one large merchant fails. Concentration context also affects reserve and monitoring priorities.
-- Logic: Sums approved transaction amount by merchant during the 30 days before the fixed as-of date, divides each amount by total portfolio approved volume in that window, and ranks merchants by volume. Cumulative share follows that descending rank; declined and reversed attempts are excluded. This is an exposure and portfolio-summary query, not a merchant risk signal, so its configured watchlist weight is zero.
-- Thresholds: Illustrative thresholds are a 30-day lookback and the top 10 merchants by approved volume, with no minimum concentration share. A real portfolio would tune lookback, segmentation, exposure measures, and escalation levels to its risk appetite.
-- Likely false positives: Large enterprise merchants, seasonal merchants such as M0198, and contract-driven merchants such as M0200 can legitimately appear near the top. The query retains them because concentration is measured rather than treated as misconduct.
-- Next step: Review the largest exposures against reserves, settlement timing, financial condition, and contingency plans; then decide whether monitoring, underwriting updates, or concentration limits are warranted.
-- Output columns: portfolio_rank = descending approved-volume rank; merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; approved_transactions = approved transactions in the window; approved_volume_cents = total approved amount; portfolio_volume_share = merchant volume divided by portfolio volume; cumulative_volume_share = cumulative share through the merchant's rank; reason = plain-English explanation of the exposure.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-reporting parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        30 AS lookback_days,
        10 AS maximum_results
),
merchant_approved_volume AS (
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
portfolio_approved_volume AS (
    SELECT sum(approved_volume_cents) AS total_approved_volume_cents
    FROM merchant_approved_volume
),
ranked_merchant_volume AS (
    SELECT
        merchant_approved_volume.merchant_id,
        merchant_approved_volume.approved_transactions,
        merchant_approved_volume.approved_volume_cents,
        row_number() OVER (
            ORDER BY merchant_approved_volume.approved_volume_cents DESC
        ) AS portfolio_rank,
        merchant_approved_volume.approved_volume_cents::DOUBLE
            / portfolio_approved_volume.total_approved_volume_cents
            AS portfolio_volume_share,
        sum(merchant_approved_volume.approved_volume_cents) OVER (
            ORDER BY merchant_approved_volume.approved_volume_cents DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )::DOUBLE / portfolio_approved_volume.total_approved_volume_cents
            AS cumulative_volume_share
    FROM merchant_approved_volume
    CROSS JOIN portfolio_approved_volume
)
SELECT
    ranked_merchant_volume.portfolio_rank,
    ranked_merchant_volume.merchant_id,
    merchant.merchant_name,
    ranked_merchant_volume.approved_transactions,
    ranked_merchant_volume.approved_volume_cents,
    round(ranked_merchant_volume.portfolio_volume_share, 4) AS portfolio_volume_share,
    round(ranked_merchant_volume.cumulative_volume_share, 4) AS cumulative_volume_share,
    printf(
        'Rank %d with $%.2f approved volume; %.2f%% of 30-day portfolio volume',
        ranked_merchant_volume.portfolio_rank,
        ranked_merchant_volume.approved_volume_cents / 100.0,
        ranked_merchant_volume.portfolio_volume_share * 100
    ) AS reason
FROM ranked_merchant_volume
CROSS JOIN parameters
JOIN merchants AS merchant USING (merchant_id)
WHERE ranked_merchant_volume.portfolio_rank <= parameters.maximum_results
ORDER BY ranked_merchant_volume.portfolio_rank;
