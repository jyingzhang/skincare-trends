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
    CAST(probed_at AS TIMESTAMP) AS probed_at
FROM {{ source('raw', 'raw_product_search_keywords') }}
