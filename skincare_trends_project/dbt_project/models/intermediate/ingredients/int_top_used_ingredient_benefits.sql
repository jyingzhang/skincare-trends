/*
Purpose: Normalize curated ingredient benefits into one row per benefit.
Grain: Ingredient x Benefit
*/

WITH base AS (
    SELECT *
    FROM {{ ref('int_top_used_ingredients_seed') }}
),

split_benefits AS (
    SELECT
        b.ingredient_name,
        TRIM({{ unnest_col('benefit_raw') }}) AS benefit_name
    FROM base AS b
    {{ cross_join_unnest_split("COALESCE(b.benefits_raw, '')", "','", 'benefit_raw') }}
    WHERE NULLIF(TRIM({{ unnest_col('benefit_raw') }}), '') IS NOT NULL
)

SELECT
    ingredient_name,
    benefit_name
FROM split_benefits
GROUP BY ALL
