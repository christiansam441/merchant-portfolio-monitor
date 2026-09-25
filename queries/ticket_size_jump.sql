-- Title: Sudden Ticket-Size Increase
-- Category: Activity Change
-- Severity: Medium | A large ticket shift changes potential loss size but may reflect legitimate product or customer changes.
-- What it flags: Merchants whose recent average approved ticket is far above both their earlier approved-ticket average and their declared typical ticket. It also requires meaningful transaction counts in both periods.
-- Why it matters: A sudden ticket increase can indicate account takeover, an undeclared business-model change, transaction laundering, or higher per-transaction loss exposure than underwriting anticipated. Comparing with both history and declared activity reduces noise.
-- Logic: Calculates count-based average approved transaction amount before the final 7-day window and during that window. Recent average ticket must be at least 4 times the historical average and 3 times the merchant's declared typical ticket; declined and reversed attempts are excluded.
-- Thresholds: Illustrative thresholds are at least 100 approved transactions in each period, a 7-day recent window, a recent average at least 4 times historical average, and at least 3 times declared typical ticket. All thresholds would be tuned to a real portfolio and merchant segment.
-- Likely false positives: Enterprise contracts, product launches, wholesale orders, or product-mix changes can legitimately increase ticket size. M0200 is the contract-driven decoy; it is excluded because its recent tickets remain consistent with its declared typical ticket even though they exceed earlier history.
-- Next step: Review high-value transaction samples and customer concentration, request invoices or contracts supporting the change, compare products with the declared business model, contact the merchant, update underwriting if legitimate, and consider a reserve or hold if the increase is unexplained.
-- Output columns: merchant_id = synthetic merchant identifier; merchant_name = synthetic display name; historical_transactions = approved transactions before the recent window; historical_average_ticket_cents = their average amount; recent_transactions = approved transactions in the recent window; recent_average_ticket_cents = their average amount; declared_typical_ticket_cents = merchant-declared typical amount; historical_ticket_multiple = recent average divided by historical average; declared_ticket_multiple = recent average divided by declared typical ticket; reason = plain-English explanation of the flag.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameters.
    SELECT
        TIMESTAMPTZ '2026-09-24 00:00:00+00' AS as_of_date,
        7 AS recent_window_days,
        100 AS minimum_period_transactions,
        4.0 AS minimum_historical_multiple,
        3.0 AS minimum_declared_multiple
),
approved_ticket_windows AS (
    SELECT
        transaction.merchant_id,
        count(*) FILTER (
            WHERE transaction.occurred_at < parameters.as_of_date
                - parameters.recent_window_days * INTERVAL '1 day'
        ) AS historical_transactions,
        avg(transaction.amount_cents) FILTER (
            WHERE transaction.occurred_at < parameters.as_of_date
                - parameters.recent_window_days * INTERVAL '1 day'
        ) AS historical_average_ticket_cents,
        count(*) FILTER (
            WHERE transaction.occurred_at >= parameters.as_of_date
                - parameters.recent_window_days * INTERVAL '1 day'
              AND transaction.occurred_at < parameters.as_of_date
        ) AS recent_transactions,
        avg(transaction.amount_cents) FILTER (
            WHERE transaction.occurred_at >= parameters.as_of_date
                - parameters.recent_window_days * INTERVAL '1 day'
              AND transaction.occurred_at < parameters.as_of_date
        ) AS recent_average_ticket_cents
    FROM transactions AS transaction
    CROSS JOIN parameters
    WHERE transaction.status = 'approved'
    GROUP BY transaction.merchant_id
),
ticket_comparison AS (
    SELECT
        approved_ticket_windows.merchant_id,
        approved_ticket_windows.historical_transactions,
        approved_ticket_windows.historical_average_ticket_cents,
        approved_ticket_windows.recent_transactions,
        approved_ticket_windows.recent_average_ticket_cents,
        merchant.typical_ticket_cents AS declared_typical_ticket_cents,
        approved_ticket_windows.recent_average_ticket_cents
            / approved_ticket_windows.historical_average_ticket_cents
            AS historical_ticket_multiple,
        approved_ticket_windows.recent_average_ticket_cents
            / merchant.typical_ticket_cents
            AS declared_ticket_multiple
    FROM approved_ticket_windows
    JOIN merchants AS merchant USING (merchant_id)
)
SELECT
    ticket_comparison.merchant_id,
    merchant.merchant_name,
    ticket_comparison.historical_transactions,
    round(ticket_comparison.historical_average_ticket_cents, 2)
        AS historical_average_ticket_cents,
    ticket_comparison.recent_transactions,
    round(ticket_comparison.recent_average_ticket_cents, 2)
        AS recent_average_ticket_cents,
    ticket_comparison.declared_typical_ticket_cents,
    round(ticket_comparison.historical_ticket_multiple, 2) AS historical_ticket_multiple,
    round(ticket_comparison.declared_ticket_multiple, 2) AS declared_ticket_multiple,
    printf(
        '$%.2f recent average ticket, %.2fx historical and %.2fx declared typical ticket',
        ticket_comparison.recent_average_ticket_cents / 100.0,
        ticket_comparison.historical_ticket_multiple,
        ticket_comparison.declared_ticket_multiple
    ) AS reason
FROM ticket_comparison
CROSS JOIN parameters
JOIN merchants AS merchant USING (merchant_id)
WHERE ticket_comparison.historical_transactions >= parameters.minimum_period_transactions
  AND ticket_comparison.recent_transactions >= parameters.minimum_period_transactions
  AND ticket_comparison.historical_ticket_multiple >= parameters.minimum_historical_multiple
  AND ticket_comparison.declared_ticket_multiple >= parameters.minimum_declared_multiple
ORDER BY ticket_comparison.historical_ticket_multiple DESC, ticket_comparison.merchant_id;
