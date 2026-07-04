/*
Purpose: Aggregate Sephora review sentiment at the ingredient level.
A review is attributed to every ingredient in the product's formula.
Sentiment uses star ratings (1-5) and is_recommended — no NLP required.
Grain: Ingredient
*/

WITH ingredient_reviews AS (
    SELECT
        pi.ingredient_name,
        r.rating,
        r.is_recommended
    FROM {{ ref('stg_sephora_reviews') }} AS r
    INNER JOIN {{ ref('int_sephora_product_ingredients') }} AS pi
        ON r.product_id = pi.product_id
)

SELECT
    ingredient_name,
    COUNT(*) AS review_count,
    ROUND(AVG(rating), 2) AS avg_rating,
    ROUND(AVG(is_recommended), 2) AS recommend_rate,
    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) AS positive_reviews,
    SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
    ROUND(AVG((rating - 3) / 2.0), 2) AS avg_sentiment_score
FROM ingredient_reviews
GROUP BY ALL
