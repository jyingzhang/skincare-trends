/*
Purpose: Extract and normalize ingredients from Sephora product data.
Grain: Product x Ingredient
*/

WITH split_ingredients AS (
    {{ select_unnest_split('ingredients', "', '", 'ingredient_name') }}
),

normalized AS (
    SELECT
        product_id,
        TRIM({{ regexp_replace_all("TRIM(ingredient_name)", "\\\\s+", " ") }}) AS ingredient_name
    FROM split_ingredients
    WHERE ingredient_name != ''
        AND ingredient_name NOT LIKE '%[%'
),

cleaned AS (
    SELECT
        product_id,
        {{ clean_ingredient_name('ingredient_name') }} AS ingredient_name
    FROM normalized
)

SELECT
    ingredient_name,
    product_id
FROM cleaned
WHERE ingredient_name != ''
GROUP BY ALL
