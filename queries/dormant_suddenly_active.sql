-- Title: Dormant Merchant Reactivation
-- Category: Activity Change
-- Severity: High | Sudden reuse after a long quiet period can indicate account takeover or a material change in control.
-- What it flags: Previously active merchants with no transactions during a defined inactivity gap followed by substantial transaction activity in the last seven days.
-- Why it matters: Abrupt reactivation can indicate account takeover, merchant resale, changed business control, or unauthorized reuse of dormant credentials. The first days after reactivation can concentrate loss before normal monitoring adapts.
-- Logic: Counts all transaction attempts, regardless of status or amount, in three mutually exclusive UTC periods: historical activity before 2026-05-27, an inactivity gap from 2026-05-27 through 2026-09-16, and recent activity from 2026-09-17 through the as-of date. A merchant must have historical activity, exactly zero gap activity, and qualifying recent activity.
-- Thresholds: Illustrative thresholds are at least 100 historical transactions, zero transactions during the 113-day inactivity gap, and at least 100 transactions in the 7-day reactivation window. All thresholds would be tuned to a real portfolio and operating cadence.
-- Likely false positives: Seasonal businesses, planned reopening, platform migration, or temporary closure can create legitimate stop-and-start activity. M0198 is the seasonal-volume decoy; it is excluded because it has transaction activity inside the required inactivity gap.
-- Next step: Confirm current operating status and ownership, compare devices, sources, products, contacts, and settlement details before and after reactivation, contact the merchant through a verified channel, and apply a temporary hold or step-up review if account takeover remains plausible.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; historical_transactions = transactions before the inactivity gap; inactivity_gap_transactions = transactions during the required quiet period; recent_transactions = transactions in the reactivation window; reactivated_at_utc = first recent transaction time in UTC; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-05-27 00:00:00+00' AS inactivity_start_date,
        TIMESTAMPTZ '2026-09-17 00:00:00+00' AS reactivation_start_date,
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        100 AS minimum_historical_transactions,
        0 AS maximum_gap_transactions,
        100 AS minimum_recent_transactions
),
merchant_activity_windows AS (
    SELECT
        transaction.merchant_id,
        count(*) FILTER (
            WHERE transaction.occurred_at < parameters.inactivity_start_date
        ) AS historical_transactions,
        count(*) FILTER (
            WHERE transaction.occurred_at >= parameters.inactivity_start_date
              AND transaction.occurred_at < parameters.reactivation_start_date
        ) AS inactivity_gap_transactions,
        count(*) FILTER (
            WHERE transaction.occurred_at >= parameters.reactivation_start_date
              AND transaction.occurred_at < parameters.as_of_date
        ) AS recent_transactions,
        min(transaction.occurred_at) FILTER (
            WHERE transaction.occurred_at >= parameters.reactivation_start_date
              AND transaction.occurred_at < parameters.as_of_date
        ) AS reactivated_at
    FROM transactions AS transaction
    CROSS JOIN parameters
    GROUP BY transaction.merchant_id
),
qualifying_reactivations AS (
    SELECT merchant_activity_windows.*
    FROM merchant_activity_windows
    CROSS JOIN parameters
    WHERE merchant_activity_windows.historical_transactions
            >= parameters.minimum_historical_transactions
      AND merchant_activity_windows.inactivity_gap_transactions
            <= parameters.maximum_gap_transactions
      AND merchant_activity_windows.recent_transactions
            >= parameters.minimum_recent_transactions
)
SELECT
    qualifying_reactivations.merchant_id,
    merchant.merchant_name,
    qualifying_reactivations.historical_transactions,
    qualifying_reactivations.inactivity_gap_transactions,
    qualifying_reactivations.recent_transactions,
    strftime(
        qualifying_reactivations.reactivated_at,
        '%Y-%m-%dT%H:%M:%SZ'
    ) AS reactivated_at_utc,
    printf(
        '%d transactions after a 113-day gap with no activity; %d historical transactions',
        qualifying_reactivations.recent_transactions,
        qualifying_reactivations.historical_transactions
    ) AS reason
FROM qualifying_reactivations
JOIN merchants AS merchant USING (merchant_id)
ORDER BY qualifying_reactivations.recent_transactions DESC, qualifying_reactivations.merchant_id;
