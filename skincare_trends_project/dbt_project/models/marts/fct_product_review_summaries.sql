/*
Purpose: Mart combining product review summaries with review stats.
Grain: Product
*/

WITH rating_counts AS (
    SELECT
        product_id,
        rating,
        COUNT(*) AS count
    FROM {{ ref('stg_sephora_reviews') }}
    GROUP BY ALL
),

product_lvl_rating_counts AS (
    SELECT
        product_id,
        {{ rating_counts_array() }} AS rating_counts
    FROM rating_counts
    GROUP BY product_id
),

recommended_counts AS (
    SELECT
        product_id,
        COUNT(*) AS recommended_count
    FROM {{ ref('stg_sephora_reviews') }}
    WHERE is_recommended = 1.0
    GROUP BY product_id
)

SELECT
    p.product_id,
    p.product_name,
    p.brand_name,
    s.price_usd,
    s.ingredients,
    p.total_review_count,
    prc.rating_counts,
    rc.recommended_count,
    p.avg_rating,
    p.review_sample_size,
    p.summary,
    p.model_name,
    p.summarized_at
FROM {{ ref('stg_product_review_summaries') }} AS p
INNER JOIN {{ ref('stg_sephora_products') }} AS s
    ON p.product_id = s.product_id
INNER JOIN product_lvl_rating_counts AS prc
    ON p.product_id = prc.product_id
INNER JOIN recommended_counts AS rc
    ON p.product_id = rc.product_id
