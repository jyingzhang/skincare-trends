/*
Purpose: Stage AI-generated product review summaries from OpenAI ingest.
*/

SELECT
    product_id,
    product_name,
    brand_name,
    total_review_count,
    avg_rating,
    review_sample_size,
    summary,
    model_name,
    summarized_at
FROM {{ source('raw', 'raw_product_review_summaries') }}
