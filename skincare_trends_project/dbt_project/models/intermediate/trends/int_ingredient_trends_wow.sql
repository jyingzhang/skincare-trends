{{ config_partitioned_trends(cluster_by=['ingredient_name'], partition_field='snapshot_date') }}

/*
Purpose: Week-over-week search interest change for every observed ingredient snapshot.
Grain: snapshot_date x ingredient_name
Notes: Compares each snapshot to the prior observed snapshot for that ingredient (LAG, not calendar day).
*/

WITH trends AS (
    SELECT
        date,
        ingredient_name,
        normalized_search_interest
    FROM {{ ref('int_ingredient_trends_normalized') }}
),

with_wow AS (
    SELECT
        date AS snapshot_date,
        ingredient_name,
        normalized_search_interest AS current_search_interest,
        LAG(date) OVER (
            PARTITION BY ingredient_name
            ORDER BY date
        ) AS previous_snapshot_date,
        LAG(normalized_search_interest) OVER (
            PARTITION BY ingredient_name
            ORDER BY date
        ) AS previous_search_interest
    FROM trends
)

SELECT
    snapshot_date,
    ingredient_name,
    previous_snapshot_date,
    current_search_interest,
    previous_search_interest,
    current_search_interest - previous_search_interest AS wow_search_interest_delta
FROM with_wow
