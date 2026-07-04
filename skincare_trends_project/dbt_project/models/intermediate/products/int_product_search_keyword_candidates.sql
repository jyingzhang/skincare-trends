/*
Purpose: All Google Trends keyword candidates per pilot product (LLM + rule-based).
Grain: product_id x candidate_rank
*/

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
    generated_at
FROM {{ ref('stg_product_search_keyword_candidates') }}
