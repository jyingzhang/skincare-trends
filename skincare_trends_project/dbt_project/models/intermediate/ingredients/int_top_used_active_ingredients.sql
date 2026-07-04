/*
Purpose: Get the top used active ingredients from Sephora product data.
*/

WITH distinct_ingredients AS (
    SELECT 
        DISTINCT a.ingredient_name
    FROM {{ ref('int_sephora_product_ingredients') }} a
    INNER JOIN {{ ref('ingredients_with_active_flag') }} b
        ON a.ingredient_name = b.ingredient_name
    WHERE b.is_active = 1   -- or = 1 if dbt loads it as integer
)

SELECT
    a.ingredient_name,
    COUNT(DISTINCT b.product_id) AS product_count
FROM distinct_ingredients a
INNER JOIN {{ ref('int_sephora_product_ingredients') }} b
    ON a.ingredient_name = b.ingredient_name
GROUP BY ALL
HAVING product_count >= 10 -- filter out ingredients that are not used in at least 10 products
ORDER BY 2 DESC
