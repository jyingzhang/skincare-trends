-- Fail if either trends mart is stale by more than 45 days.
WITH latest_dates AS (
    SELECT
        'product' AS dataset,
        MAX(date) AS max_date
    FROM {{ ref('fct_product_trends') }}

    UNION ALL

    SELECT
        'ingredient' AS dataset,
        MAX(date) AS max_date
    FROM {{ ref('fct_ingredients_trends') }}
)

SELECT
    dataset,
    max_date
FROM latest_dates
WHERE max_date < CURRENT_DATE - INTERVAL 45 DAY
