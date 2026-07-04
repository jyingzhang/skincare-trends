/*
Purpose: Candidate ingredient cohort for Google Trends ingredient pulls.
Grain: Ingredient
*/

SELECT
    a.ingredient_name,
    a.product_count,
    ROW_NUMBER() OVER (
        ORDER BY a.product_count DESC, a.ingredient_name
    ) AS trend_rank
FROM {{ ref('int_top_used_active_ingredients') }} AS a
