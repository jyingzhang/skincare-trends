-- Fail if mart grain is not unique: date x ingredient_name
SELECT
    date,
    ingredient_name,
    COUNT(*) AS row_count
FROM {{ ref('fct_ingredients_trends') }}
GROUP BY 1, 2
HAVING COUNT(*) > 1
