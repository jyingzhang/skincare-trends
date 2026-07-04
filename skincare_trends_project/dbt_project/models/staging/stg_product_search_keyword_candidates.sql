SELECT
    product_id,
    product_name,
    brand_name,
    review_count_rank,
    candidate_rank,
    search_keyword,
    source,
    hero_words,
    product_type,
    CAST(generated_at AS TIMESTAMP) AS generated_at
FROM {{ source('raw', 'raw_product_search_keyword_candidates') }}
