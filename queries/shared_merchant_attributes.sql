-- Title: Shared Merchant Identity Attributes
-- Category: Linkage
-- Severity: Medium | Exact shared identity or settlement attributes can connect merchant risk, but legitimate business relationships are common.
-- What it flags: Merchant pairs sharing an exact synthetic bank account, owner phone, or business address token. Both merchants in each relationship are returned so an analyst can review the full linkage cluster.
-- Why it matters: Shared onboarding attributes can reveal undisclosed common control, coordinated abuse, duplicate accounts, or movement of activity between merchants. Linkage should be evaluated with transaction behavior and verified ownership before action.
-- Logic: Identifies attribute values used by at least two merchants, creates unique merchant pairs for each shared value, then expands each pair so both linked merchants appear. Matching is exact within each synthetic token field; fuzzy identity matching is not performed.
-- Thresholds: The illustrative threshold is an exact attribute token shared by at least 2 merchants. A real portfolio would tune cluster size, attribute reliability, fuzzy matching, and known-enterprise suppressions to its onboarding data.
-- Likely false positives: Legitimate multi-location businesses, franchise businesses, parent and subsidiary entities, shared offices, and treasury arrangements can share attributes. None of the three current decoys shares an identity attribute, so no decoy-specific exclusion is applied.
-- Next step: Compare beneficial ownership and onboarding records, verify contact and bank-account authority, confirm any franchise or multi-location relationship, review cross-merchant transaction and settlement patterns, and contact the merchants before restricting linked accounts.
-- Output columns: merchant_id = synthetic merchant in the linkage; merchant_name = its synthetic display name; linked_merchant_id = other merchant in the pair; linked_merchant_name = other synthetic display name; shared_attribute = bank_account, owner_phone, or business_address; shared_value = synthetic matched token; cluster_size = merchants using the matched value; reason = plain-English explanation of the linkage.
-- Data notes: Fixed as-of date 2026-09-24 00:00:00 UTC. All merchant, transaction, refund, and chargeback data is synthetic and reproducibly generated.

WITH parameters AS (
    -- Illustrative portfolio-tuning parameter.
    SELECT 2 AS minimum_cluster_size
),
attribute_values AS (
    SELECT merchant_id, 'bank_account' AS shared_attribute, bank_account_token AS shared_value
    FROM merchants
    UNION ALL
    SELECT merchant_id, 'owner_phone' AS shared_attribute, owner_phone_token AS shared_value
    FROM merchants
    UNION ALL
    SELECT merchant_id, 'business_address' AS shared_attribute, address_token AS shared_value
    FROM merchants
),
shared_attribute_values AS (
    SELECT
        attribute_values.shared_attribute,
        attribute_values.shared_value,
        count(*) AS cluster_size
    FROM attribute_values
    GROUP BY attribute_values.shared_attribute, attribute_values.shared_value
    HAVING count(*) >= (SELECT minimum_cluster_size FROM parameters)
),
unique_merchant_pairs AS (
    SELECT
        left_attribute.merchant_id AS merchant_a_id,
        right_attribute.merchant_id AS merchant_b_id,
        left_attribute.shared_attribute,
        left_attribute.shared_value,
        shared_attribute_values.cluster_size
    FROM attribute_values AS left_attribute
    JOIN attribute_values AS right_attribute
      ON left_attribute.shared_attribute = right_attribute.shared_attribute
     AND left_attribute.shared_value = right_attribute.shared_value
     AND left_attribute.merchant_id < right_attribute.merchant_id
    JOIN shared_attribute_values
      ON left_attribute.shared_attribute = shared_attribute_values.shared_attribute
     AND left_attribute.shared_value = shared_attribute_values.shared_value
),
directional_linkages AS (
    SELECT
        merchant_a_id AS merchant_id,
        merchant_b_id AS linked_merchant_id,
        shared_attribute,
        shared_value,
        cluster_size
    FROM unique_merchant_pairs
    UNION ALL
    SELECT
        merchant_b_id AS merchant_id,
        merchant_a_id AS linked_merchant_id,
        shared_attribute,
        shared_value,
        cluster_size
    FROM unique_merchant_pairs
)
SELECT
    directional_linkages.merchant_id,
    merchant.merchant_name,
    directional_linkages.linked_merchant_id,
    linked_merchant.merchant_name AS linked_merchant_name,
    directional_linkages.shared_attribute,
    directional_linkages.shared_value,
    directional_linkages.cluster_size,
    printf(
        '%s shared with %s in a %d-merchant cluster',
        replace(directional_linkages.shared_attribute, '_', ' '),
        directional_linkages.linked_merchant_id,
        directional_linkages.cluster_size
    ) AS reason
FROM directional_linkages
JOIN merchants AS merchant
  ON directional_linkages.merchant_id = merchant.merchant_id
JOIN merchants AS linked_merchant
  ON directional_linkages.linked_merchant_id = linked_merchant.merchant_id
ORDER BY
    directional_linkages.shared_attribute,
    directional_linkages.shared_value,
    directional_linkages.merchant_id,
    directional_linkages.linked_merchant_id;
