/*
Purpose: Canonical ingredient lookup from curated seed.
Grain: Ingredient
*/

WITH normalized AS (
    SELECT
        {{ clean_ingredient_name('ingredient_name') }} AS ingredient_name,
        ingredient_name AS ingredient_name_raw,
        CAST(product_count AS INTEGER) AS product_count,
        NULLIF(TRIM(benefits), '') AS benefits_raw,
        NULLIF(TRIM(commonly_known_as), '') AS commonly_known_as_raw,
        NULLIF(TRIM(ingredient_definition), '') AS ingredient_definition
    FROM {{ ref('top_used_ingredients_benefits') }}
    WHERE NULLIF(TRIM(ingredient_name), '') IS NOT NULL
)

SELECT
    ingredient_name,
    MAX(ingredient_name_raw) AS ingredient_name_raw,
    MAX(product_count) AS product_count,
    MAX(benefits_raw) AS benefits_raw,
    MAX(commonly_known_as_raw) AS commonly_known_as_raw,
    MAX(ingredient_definition) AS ingredient_definition
FROM normalized
GROUP BY ALL
