/*
Purpose: Product-level Google Trends mart for the pilot cohort.
Grain: date x product
Notes (anchorless / self-scaled):
  - search_interest is each product's own 0-100 scale (100 = its 12-month peak),
    so it measures momentum/breakout, not absolute popularity.
  - active_weeks + has_reliable_signal separate sustained interest from one-week
    noise spikes; is_weekly_peak flags a product at/near its own 12-month high.
*/

{{ config_partitioned_trends(cluster_by=['product_id']) }}

{% set reliable_min_weeks = 13 %}
{% set peak_threshold = 90 %}

WITH signal AS (
    SELECT
        product_id,
        MAX(raw_search_interest) > 0 AS has_trends_signal,
        COUNTIF(raw_search_interest > 0) AS active_weeks
    FROM {{ ref('int_product_trends_normalized') }}
    GROUP BY product_id
)

SELECT
    t.date,
    p.product_id,
    p.product_name,
    p.brand_name,
    p.primary_category,
    p.secondary_category,
    p.search_keyword,
    p.probed_search_keyword,
    p.has_probe_signal,
    s.has_trends_signal,
    s.active_weeks,
    s.active_weeks >= {{ reliable_min_weeks }} AS has_reliable_signal,
    t.normalized_search_interest >= {{ peak_threshold }} AS is_weekly_peak,
    p.total_reviews,
    p.review_count_rank,
    p.cv_monthly_reviews,
    p.half_life_growth_ratio,
    p.stability_rank,
    t.raw_search_interest AS search_interest_raw,
    t.normalized_search_interest AS search_interest
FROM {{ ref('int_product_trends_normalized') }} AS t
INNER JOIN {{ ref('int_pilot_products') }} AS p
    ON t.product_id = p.product_id
INNER JOIN signal AS s
    ON t.product_id = s.product_id
