-- Title: Shared Settlement Bank Account
-- Category: Linkage
-- Severity: Medium | A shared settlement destination is a meaningful ownership link but requires business-context validation before action.
-- What it flags: The newest merchant sharing a synthetic settlement bank token with at least one older merchant. The older account holder is retained as linkage evidence but is not itself flagged by this query.
-- Why it matters: Shared settlement destinations can reveal undisclosed common control, merchant-account recycling, fund diversion, or coordinated abuse across nominally separate businesses. The link is investigative evidence, not proof of wrongdoing.
-- Logic: Groups merchants by bank account token, keeps tokens linked to two or more merchants with different creation dates, and returns only the newest merchant on each token. Merchants tied for newest creation date would all be returned; transaction behavior and bank-account ownership are not scored here.
-- Thresholds: Illustrative thresholds are at least 2 merchants on one settlement token and different merchant creation dates, with only the newest merchant prioritized. These rules would be tuned to a real portfolio and verified against the institution's onboarding and linkage policies.
-- Likely false positives: Legitimate multi-location businesses, franchise businesses, parent and subsidiary entities, payment facilitators, and businesses using a shared treasury account can share settlement details. None of the three current decoys shares a bank token, so no decoy-specific exclusion is applied.
-- Next step: Compare beneficial ownership and onboarding records, request proof of bank-account ownership, confirm any franchise or multi-location relationship, review cross-merchant settlement and transaction patterns, contact the merchants if needed, and restrict settlement only when the linkage creates substantiated risk.
-- Output columns: merchant_id = newer synthetic merchant prioritized for review; merchant_name = synthetic display name; bank_account_token = synthetic shared settlement token; linked_merchant_count = merchants using the token; linked_merchant_ids = other synthetic merchants using it; merchant_created_at_utc = prioritized merchant creation time; first_linked_merchant_created_at_utc = earliest creation time on the token; reason = plain-English explanation of the linkage.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameter.
    SELECT 2 AS minimum_linked_merchants
),
bank_account_summary AS (
    SELECT
        merchant.bank_account_token,
        count(*) AS linked_merchant_count,
        min(merchant.created_at) AS first_merchant_created_at,
        max(merchant.created_at) AS newest_merchant_created_at
    FROM merchants AS merchant
    GROUP BY merchant.bank_account_token
),
shared_bank_accounts AS (
    SELECT bank_account_summary.*
    FROM bank_account_summary
    CROSS JOIN parameters
    WHERE bank_account_summary.linked_merchant_count >= parameters.minimum_linked_merchants
      AND bank_account_summary.first_merchant_created_at
            < bank_account_summary.newest_merchant_created_at
),
newest_linked_merchants AS (
    SELECT
        merchant.merchant_id,
        merchant.merchant_name,
        merchant.bank_account_token,
        merchant.created_at,
        shared_bank_accounts.linked_merchant_count,
        shared_bank_accounts.first_merchant_created_at
    FROM shared_bank_accounts
    JOIN merchants AS merchant
      ON shared_bank_accounts.bank_account_token = merchant.bank_account_token
     AND shared_bank_accounts.newest_merchant_created_at = merchant.created_at
),
linkage_details AS (
    SELECT
        newest_linked_merchants.merchant_id,
        newest_linked_merchants.merchant_name,
        newest_linked_merchants.bank_account_token,
        newest_linked_merchants.created_at,
        newest_linked_merchants.linked_merchant_count,
        newest_linked_merchants.first_merchant_created_at,
        string_agg(other_merchant.merchant_id, ', ' ORDER BY other_merchant.merchant_id)
            AS linked_merchant_ids
    FROM newest_linked_merchants
    JOIN merchants AS other_merchant
      ON newest_linked_merchants.bank_account_token = other_merchant.bank_account_token
     AND newest_linked_merchants.merchant_id <> other_merchant.merchant_id
    GROUP BY
        newest_linked_merchants.merchant_id,
        newest_linked_merchants.merchant_name,
        newest_linked_merchants.bank_account_token,
        newest_linked_merchants.created_at,
        newest_linked_merchants.linked_merchant_count,
        newest_linked_merchants.first_merchant_created_at
)
SELECT
    linkage_details.merchant_id,
    linkage_details.merchant_name,
    linkage_details.bank_account_token,
    linkage_details.linked_merchant_count,
    linkage_details.linked_merchant_ids,
    strftime(linkage_details.created_at, '%Y-%m-%dT%H:%M:%SZ') AS merchant_created_at_utc,
    strftime(
        linkage_details.first_merchant_created_at,
        '%Y-%m-%dT%H:%M:%SZ'
    ) AS first_linked_merchant_created_at_utc,
    printf(
        'Settlement account shared by %d merchants; newer merchant linked to %s',
        linkage_details.linked_merchant_count,
        linkage_details.linked_merchant_ids
    ) AS reason
FROM linkage_details
ORDER BY linkage_details.linked_merchant_count DESC, linkage_details.merchant_id;
