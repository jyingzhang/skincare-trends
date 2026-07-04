/*
Purpose: Probed winning Google Trends keyword per pilot product.
Grain: product_id
*/

SELECT
    product_id,
    product_name,
    brand_name,
    review_count_rank,
    search_keyword,
    hero_words,
    product_type,
    candidate_rank,
    candidate_source,
    probe_avg_interest,
    probe_max_interest,
    probe_nonzero_weeks,
    probe_total_weeks,
    probe_avg_interest > 0 AS has_probe_signal,
    probed_at
FROM {{ ref('stg_product_search_keywords') }}
