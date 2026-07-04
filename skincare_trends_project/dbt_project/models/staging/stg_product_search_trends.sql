/*
Purpose: Stage Google Trends search interest for pilot products.
*/

SELECT
    {{ cast_trend_date('date') }} AS date,
    product_id,
    search_keyword,
    search_interest
FROM {{ source('raw', 'raw_product_trends') }}
WHERE is_anchor = false
