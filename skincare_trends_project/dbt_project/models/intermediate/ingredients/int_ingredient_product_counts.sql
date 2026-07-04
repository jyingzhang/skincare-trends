/*
Purpose: Product counts per ingredient across catalog, pilot cohort, and trends-tracked products.
Grain: ingredient_name

Notes:
  - product_count (from seed) = Sephora catalog products containing the ingredient (~951 for tocopherol).
  - pilot_product_count = top-200 pilot cohort products containing the ingredient (<= 200).
  - trends_tracked_product_count = pilot products with Google Trends rows (~163 in product mart).
*/

WITH pilot_products AS (
    SELECT product_id
    FROM {{ ref('int_pilot_products') }}
),

trends_products AS (
    SELECT DISTINCT product_id
    FROM {{ ref('int_product_trends_normalized') }}
),

ingredient_products AS (
    SELECT
        ingredient_name,
        product_id
    FROM {{ ref('int_sephora_product_ingredients') }}
)

SELECT
    s.ingredient_name,
    s.product_count,
    COUNT(DISTINCT CASE
        WHEN pp.product_id IS NOT NULL THEN ip.product_id
    END) AS pilot_product_count,
    COUNT(DISTINCT CASE
        WHEN tp.product_id IS NOT NULL THEN ip.product_id
    END) AS trends_tracked_product_count
FROM {{ ref('int_top_used_ingredients_seed') }} AS s
LEFT JOIN ingredient_products AS ip
    ON s.ingredient_name = ip.ingredient_name
LEFT JOIN pilot_products AS pp
    ON ip.product_id = pp.product_id
LEFT JOIN trends_products AS tp
    ON ip.product_id = tp.product_id
GROUP BY ALL
