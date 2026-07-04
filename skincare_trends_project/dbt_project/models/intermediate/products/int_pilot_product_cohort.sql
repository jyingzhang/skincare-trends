/*
Purpose: Top 200 skincare pilot products (metadata only, no Google Trends keyword).
Grain: product_id
*/

WITH ranked AS (
    SELECT
        s.product_id,
        s.product_name,
        s.brand_name,
        s.total_reviews,
        s.active_months,
        s.first_review_month,
        s.last_review_month,
        s.avg_monthly_reviews,
        s.cv_monthly_reviews,
        s.half_life_growth_ratio,
        s.recent_vs_prior_year_ratio,
        s.stability_rank,
        ROW_NUMBER() OVER (
            ORDER BY s.total_reviews DESC, s.product_id
        ) AS review_count_rank
    FROM {{ ref('int_product_review_stability') }} AS s
)

SELECT
    product_id,
    product_name,
    brand_name,
    total_reviews,
    review_count_rank,
    active_months,
    first_review_month,
    last_review_month,
    avg_monthly_reviews,
    cv_monthly_reviews,
    half_life_growth_ratio,
    recent_vs_prior_year_ratio,
    stability_rank,
    review_count_rank <= 200 AS is_pilot_product
FROM ranked
WHERE review_count_rank <= 200
