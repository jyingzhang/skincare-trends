/*
Purpose: Top 200 skincare products for the Google Trends product pilot.

search_keyword: probed winner from int_product_search_keywords when available,
otherwise legacy rule-based fallback from product title truncation.
*/

WITH cohort AS (
    SELECT * FROM {{ ref('int_pilot_product_cohort') }}
),

categories AS (
    SELECT
        product_id,
        primary_category,
        secondary_category
    FROM {{ ref('stg_sephora_products') }}
),

cleaned_names AS (
    SELECT
        c.*,
        TRIM(
            {{ regexp_replace_all(
                regexp_replace_all(
                    regexp_replace_all(
                        'c.product_name',
                        '\\([^)]*\\)',
                        ''
                    ),
                    '\\b(limited edition|jumbo|duo|travel size|refillable)\\b',
                    ''
                ),
                '\\s+',
                ' '
            ) }}
        ) AS cleaned_product_name
    FROM cohort AS c
),

short_names AS (
    SELECT
        c.*,
        TRIM(
            {{ regexp_replace_ci(
                'c.cleaned_product_name',
                '\\s+(with|intense|refillable|and).*$',
                ''
            ) }}
        ) AS short_product_name
    FROM cleaned_names AS c
),

legacy_keywords AS (
    SELECT
        s.*,
        TRIM(
            LOWER(
                brand_name
                || ' '
                || {{ first_n_words('short_product_name', 5) }}
                || CASE
                    WHEN {{ ilike_contains('product_name', "'%mini%'") }} THEN ' mini'
                    ELSE ''
                END
            )
        ) AS legacy_search_keyword
    FROM short_names AS s
)

SELECT
    l.product_id,
    l.product_name,
    l.brand_name,
    cat.primary_category,
    cat.secondary_category,
    COALESCE(k.search_keyword, l.legacy_search_keyword) AS search_keyword,
    k.search_keyword AS probed_search_keyword,
    l.legacy_search_keyword,
    k.hero_words,
    k.product_type,
    k.probe_avg_interest,
    k.probe_max_interest,
    k.probe_nonzero_weeks,
    k.probe_total_weeks,
    COALESCE(k.has_probe_signal, FALSE) AS has_probe_signal,
    l.total_reviews,
    l.review_count_rank,
    l.active_months,
    l.first_review_month,
    l.last_review_month,
    l.avg_monthly_reviews,
    l.cv_monthly_reviews,
    l.half_life_growth_ratio,
    l.recent_vs_prior_year_ratio,
    l.stability_rank,
    l.is_pilot_product
FROM legacy_keywords AS l
LEFT JOIN {{ ref('int_product_search_keywords') }} AS k
    ON l.product_id = k.product_id
LEFT JOIN categories AS cat
    ON l.product_id = cat.product_id
