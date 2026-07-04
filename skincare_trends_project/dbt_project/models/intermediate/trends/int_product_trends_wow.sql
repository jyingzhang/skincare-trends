{{ config_partitioned_trends(cluster_by=['product_id'], partition_field='snapshot_date') }}

/*
Purpose: Week-over-week search interest change for every observed product snapshot.
Grain: snapshot_date x product_id
Notes: Compares each snapshot to the prior observed snapshot for that product (LAG, not calendar day).
*/

WITH trends AS (
    SELECT
        date,
        product_id,
        normalized_search_interest
    FROM {{ ref('int_product_trends_normalized') }}
),

with_wow AS (
    SELECT
        date AS snapshot_date,
        product_id,
        normalized_search_interest AS current_search_interest,
        LAG(date) OVER (
            PARTITION BY product_id
            ORDER BY date
        ) AS previous_snapshot_date,
        LAG(normalized_search_interest) OVER (
            PARTITION BY product_id
            ORDER BY date
        ) AS previous_search_interest
    FROM trends
)

SELECT
    snapshot_date,
    product_id,
    previous_snapshot_date,
    current_search_interest,
    previous_search_interest,
    current_search_interest - previous_search_interest AS wow_search_interest_delta
FROM with_wow
