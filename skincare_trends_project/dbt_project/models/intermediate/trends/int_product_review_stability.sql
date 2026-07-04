/*
Purpose: Review volume stability metrics per product.

Methodology (for showing your work):
- cv_monthly_reviews: coefficient of variation of monthly review counts (lower = steadier)
- half_life_growth_ratio: reviews in 2nd half of product history / 1st half (>1 = accelerating)
- recent_vs_prior_year_ratio: avg monthly reviews in last 12m / prior 12m (>1 = recent surge)
- stability_rank: rank by cv_monthly_reviews among products with >= 500 reviews (1 = most stable)
*/

WITH monthly AS (
    SELECT * FROM {{ ref('int_product_review_velocity') }}
),

product_lifetime AS (
    SELECT
        product_id,
        MAX(product_name) AS product_name,
        MAX(brand_name) AS brand_name,
        MIN(review_month) AS first_review_month,
        MAX(review_month) AS last_review_month,
        COUNT(*) AS active_months,
        SUM(review_count) AS total_reviews,
        AVG(review_count) AS avg_monthly_reviews,
        {{ stddev('review_count') }} AS stddev_monthly_reviews
    FROM monthly
    GROUP BY product_id
),

midpoints AS (
    SELECT
        m.product_id,
        {{ date_midpoint('pl.first_review_month', 'pl.last_review_month') }} AS midpoint_month
    FROM monthly AS m
    INNER JOIN product_lifetime AS pl
        ON m.product_id = pl.product_id
    GROUP BY m.product_id, pl.first_review_month, pl.last_review_month
),

half_split AS (
    SELECT
        m.product_id,
        SUM(
            CASE
                WHEN m.review_month < mp.midpoint_month THEN m.review_count
                ELSE 0
            END
        ) AS first_half_reviews,
        SUM(
            CASE
                WHEN m.review_month >= mp.midpoint_month THEN m.review_count
                ELSE 0
            END
        ) AS second_half_reviews
    FROM monthly AS m
    INNER JOIN midpoints AS mp
        ON m.product_id = mp.product_id
    GROUP BY m.product_id
),

year_split AS (
    SELECT
        m.product_id,
        AVG(
            CASE
                WHEN m.review_month >= {{ months_before('pl.last_review_month', 12) }}
                    THEN m.review_count
            END
        ) AS avg_reviews_recent_12m,
        AVG(
            CASE
                WHEN m.review_month >= {{ months_before('pl.last_review_month', 24) }}
                    AND m.review_month < {{ months_before('pl.last_review_month', 12) }}
                    THEN m.review_count
            END
        ) AS avg_reviews_prior_12m
    FROM monthly AS m
    INNER JOIN product_lifetime AS pl
        ON m.product_id = pl.product_id
    GROUP BY m.product_id
),

scored AS (
    SELECT
        pl.product_id,
        pl.product_name,
        pl.brand_name,
        pl.total_reviews,
        pl.active_months,
        pl.first_review_month,
        pl.last_review_month,
        ROUND(pl.avg_monthly_reviews, 1) AS avg_monthly_reviews,
        ROUND(
            pl.stddev_monthly_reviews / NULLIF(pl.avg_monthly_reviews, 0),
            2
        ) AS cv_monthly_reviews,
        hs.first_half_reviews,
        hs.second_half_reviews,
        ROUND(
            hs.second_half_reviews * 1.0 / NULLIF(hs.first_half_reviews, 0),
            2
        ) AS half_life_growth_ratio,
        ROUND(ys.avg_reviews_recent_12m, 1) AS avg_reviews_recent_12m,
        ROUND(ys.avg_reviews_prior_12m, 1) AS avg_reviews_prior_12m,
        ROUND(
            ys.avg_reviews_recent_12m / NULLIF(ys.avg_reviews_prior_12m, 0),
            2
        ) AS recent_vs_prior_year_ratio
    FROM product_lifetime AS pl
    INNER JOIN half_split AS hs
        ON pl.product_id = hs.product_id
    INNER JOIN year_split AS ys
        ON pl.product_id = ys.product_id
)

SELECT
    *,
    RANK() OVER (
        ORDER BY cv_monthly_reviews ASC, total_reviews DESC
    ) AS stability_rank
FROM scored
WHERE total_reviews >= 500
