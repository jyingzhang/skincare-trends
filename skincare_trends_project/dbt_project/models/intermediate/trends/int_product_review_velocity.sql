/*
Purpose: Monthly review counts per product for velocity and stability analysis.
Grain: product_id x review_month
*/

SELECT
    r.product_id,
    MAX(r.product_name) AS product_name,
    MAX(r.brand_name) AS brand_name,
    {{ date_trunc_month('r.submission_time') }} AS review_month,
    COUNT(*) AS review_count
FROM {{ ref('stg_sephora_reviews') }} AS r
INNER JOIN {{ ref('stg_sephora_products') }} AS p
    ON r.product_id = p.product_id
GROUP BY r.product_id, review_month
