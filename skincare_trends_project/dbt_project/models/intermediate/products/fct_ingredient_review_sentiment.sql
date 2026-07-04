/*
Purpose: Ingredient level review stats.
Grain: ingredient
*/

SELECT
    s.ingredient_name,
    s.review_count,
    s.avg_rating,
    s.recommend_rate,
    s.positive_reviews,
    s.negative_reviews,
    s.avg_sentiment_score,
    a.product_count  -- optional: how many products use it
FROM {{ ref('int_ingredient_review_sentiment') }} AS s
LEFT JOIN {{ ref('int_top_used_active_ingredients') }} AS a
    ON s.ingredient_name = a.ingredient_name
