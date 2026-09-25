-- Title: Card-Testing Velocity Burst
-- Category: Velocity
-- Severity: High | Automated testing can create immediate fraud exposure and rapidly degrade authorization performance.
-- What it flags: Dense hourly bursts of very low-value attempts across many distinct cards from one source. The pattern emphasizes both velocity and a high decline rate.
-- Why it matters: Card testing can expose weak merchant controls, create issuer and processor losses, and precede larger fraudulent transactions. Fast containment can prevent the tested credentials from being monetized.
-- Logic: Groups transaction attempts by merchant, source token, and UTC clock hour during the last 7 days. It counts attempts and distinct card tokens, then calculates a count-based decline rate as declined attempts divided by all attempts in the burst.
-- Thresholds: Illustrative thresholds are amounts at or below $2.00, at least 100 attempts, at least 100 distinct cards, and a decline rate of at least 70% in one UTC hour during a 7-day lookback. All thresholds would be tuned to a real portfolio; any card-network program threshold must be verified against current program rules before use.
-- Likely false positives: A legitimate micropayment launch, transit validation process, or retry defect can create low-value declines. None of the current decoys uses many cards from one source in a qualifying hourly burst, so no decoy-specific exclusion is applied.
-- Next step: Review authorization response codes, source and device concentration, card diversity, retry timing, and later successful charges; contact the merchant about recent technical changes and apply velocity controls or a temporary hold if testing is active.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; source_token = synthetic source identifier; burst_hour_utc = UTC hour containing the peak qualifying burst; attempt_count = total attempts in that hour; distinct_cards = distinct card tokens attempted; declined_count = declined attempts; decline_rate = declined attempts divided by all attempts; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        7 AS lookback_days,
        200 AS maximum_amount_cents,
        100 AS minimum_attempts,
        100 AS minimum_distinct_cards,
        0.70 AS minimum_decline_rate
),
low_value_attempts AS (
    SELECT
        transaction.merchant_id,
        transaction.ip_token,
        transaction.card_token,
        transaction.status,
        date_trunc('hour', transaction.occurred_at) AS burst_hour
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.occurred_at >= parameters.as_of_date
          - parameters.lookback_days * INTERVAL '1 day'
      AND transaction.occurred_at < parameters.as_of_date
      AND transaction.amount_cents <= parameters.maximum_amount_cents
),
hourly_source_metrics AS (
    SELECT
        low_value_attempts.merchant_id,
        low_value_attempts.ip_token,
        low_value_attempts.burst_hour,
        count(*) AS attempt_count,
        count(DISTINCT low_value_attempts.card_token) AS distinct_cards,
        sum(CASE WHEN low_value_attempts.status = 'declined' THEN 1 ELSE 0 END)
            AS declined_count,
        round(
            sum(CASE WHEN low_value_attempts.status = 'declined' THEN 1 ELSE 0 END)::DOUBLE
                / count(*),
            4
        ) AS decline_rate
    FROM low_value_attempts
    GROUP BY
        low_value_attempts.merchant_id,
        low_value_attempts.ip_token,
        low_value_attempts.burst_hour
),
qualifying_bursts AS (
    SELECT hourly_source_metrics.*
    FROM hourly_source_metrics
    CROSS JOIN parameters
    WHERE hourly_source_metrics.attempt_count >= parameters.minimum_attempts
      AND hourly_source_metrics.distinct_cards >= parameters.minimum_distinct_cards
      AND hourly_source_metrics.decline_rate >= parameters.minimum_decline_rate
),
ranked_bursts AS (
    SELECT
        qualifying_bursts.*,
        row_number() OVER (
            PARTITION BY qualifying_bursts.merchant_id
            ORDER BY qualifying_bursts.attempt_count DESC, qualifying_bursts.burst_hour DESC
        ) AS merchant_rank
    FROM qualifying_bursts
)
SELECT
    ranked_bursts.merchant_id,
    merchant.merchant_name,
    ranked_bursts.ip_token AS source_token,
    strftime(ranked_bursts.burst_hour, '%Y-%m-%dT%H:%M:%SZ') AS burst_hour_utc,
    ranked_bursts.attempt_count,
    ranked_bursts.distinct_cards,
    ranked_bursts.declined_count,
    ranked_bursts.decline_rate,
    printf(
        '%d low-value attempts across %d cards in one hour; %.2f%% declined',
        ranked_bursts.attempt_count,
        ranked_bursts.distinct_cards,
        ranked_bursts.decline_rate * 100
    ) AS reason
FROM ranked_bursts
JOIN merchants AS merchant USING (merchant_id)
WHERE ranked_bursts.merchant_rank = 1
ORDER BY ranked_bursts.attempt_count DESC, ranked_bursts.merchant_id;
