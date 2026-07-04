/*
Purpose: Pull search trends for ingredients from Google Trends.
*/

SELECT
    {{ cast_trend_date('date') }} AS date,
    ingredient_name AS ingredient_name_raw,
    {{ clean_ingredient_name('ingredient_name') }} AS ingredient_name,
    search_interest
FROM {{ source('raw', 'raw_trends') }}
WHERE is_anchor = false -- anchor is retinol
    AND NULLIF(TRIM(ingredient_name), '') IS NOT NULL
