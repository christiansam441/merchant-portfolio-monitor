-- Title: Elevated Decline-Rate Outliers
-- Category: Portfolio
-- Severity: Medium | A sustained decline-rate outlier can indicate fraud attempts or integration failure, but it requires cause-level validation.
-- What it flags: Merchants with substantial recent attempt volume and a decline rate materially above the illustrative portfolio review level. Results are capped to the highest-rate merchants for manageable triage.
-- Why it matters: Elevated declines can signal card testing, poor traffic quality, incorrect authorization requests, or a broken integration. Persistent declines can create cost, issuer concern, and customer harm even when fraud loss has not yet occurred.
-- Logic: Counts all transaction attempts during the last 30 days and calculates a count-based decline rate as declined attempts divided by all attempts. Merchants must meet the activity and rate thresholds, then are ranked by decline rate and attempt count.
-- Thresholds: Illustrative thresholds are at least 100 attempts, a decline rate of at least 20%, a 30-day lookback, and a maximum of 20 returned merchants. All thresholds would be tuned to a real portfolio; any card-network program threshold must be verified against current program rules before use.
-- Likely false positives: Issuer outages, an incorrect merchant category, a failed integration release, or legitimate high-risk customer traffic can elevate declines. None of the three current decoys has a qualifying decline-rate pattern, so no decoy-specific exclusion is applied.
-- Next step: Review authorization response codes and time series, compare source and card concentration, contact the merchant about recent integration changes, and apply velocity controls or technical remediation based on the identified cause.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; recent_attempts = all attempts in the lookback; declined_attempts = declined attempts; approved_attempts = approved attempts; decline_rate = declined attempts divided by all attempts; portfolio_rank = rank among qualifying outliers; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        30 AS lookback_days,
        100 AS minimum_attempts,
        0.20 AS minimum_decline_rate,
        20 AS maximum_results
),
recent_authorization_activity AS (
    SELECT
        transaction.merchant_id,
        count(*) AS recent_attempts,
        count(*) FILTER (WHERE transaction.status = 'declined') AS declined_attempts,
        count(*) FILTER (WHERE transaction.status = 'approved') AS approved_attempts
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.occurred_at >= parameters.as_of_date
          - parameters.lookback_days * INTERVAL '1 day'
      AND transaction.occurred_at < parameters.as_of_date
    GROUP BY transaction.merchant_id
),
decline_metrics AS (
    SELECT
        recent_authorization_activity.*,
        round(
            recent_authorization_activity.declined_attempts::DOUBLE
                / recent_authorization_activity.recent_attempts,
            4
        ) AS decline_rate
    FROM recent_authorization_activity
),
qualifying_outliers AS (
    SELECT
        decline_metrics.*,
        row_number() OVER (
            ORDER BY decline_metrics.decline_rate DESC, decline_metrics.recent_attempts DESC
        ) AS portfolio_rank
    FROM decline_metrics
    CROSS JOIN parameters
    WHERE decline_metrics.recent_attempts >= parameters.minimum_attempts
      AND decline_metrics.decline_rate >= parameters.minimum_decline_rate
)
SELECT
    qualifying_outliers.merchant_id,
    merchant.merchant_name,
    qualifying_outliers.recent_attempts,
    qualifying_outliers.declined_attempts,
    qualifying_outliers.approved_attempts,
    qualifying_outliers.decline_rate,
    qualifying_outliers.portfolio_rank,
    printf(
        '%.2f%% decline rate across %d attempts in 30 days; portfolio outlier rank %d',
        qualifying_outliers.decline_rate * 100,
        qualifying_outliers.recent_attempts,
        qualifying_outliers.portfolio_rank
    ) AS reason
FROM qualifying_outliers
JOIN merchants AS merchant USING (merchant_id)
CROSS JOIN parameters
WHERE qualifying_outliers.portfolio_rank <= parameters.maximum_results
ORDER BY qualifying_outliers.portfolio_rank;
