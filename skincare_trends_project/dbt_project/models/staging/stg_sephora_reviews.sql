/*
Purpose: Stage Sephora product reviews for sentiment analysis.
*/

SELECT
    author_id,
    product_id,
    product_name,
    brand_name,
    rating,
    is_recommended,
    submission_time,
    review_title,
    review_text,
    skin_type
FROM {{ source('raw', 'raw_sephora_reviews') }}
WHERE rating IS NOT NULL
