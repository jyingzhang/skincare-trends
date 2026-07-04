-- Fail if normalized/raw interest falls outside expected bounds.
-- Normalized can exceed 100 when terms outpace the anchor.
-- Ingredient spikes can occasionally exceed 300 when anchor volume dips,
-- so we use a conservative upper guardrail of 400.
SELECT *
FROM {{ ref('int_ingredient_trends_normalized') }}
WHERE raw_search_interest < 0
    OR raw_search_interest > 100
    OR normalized_search_interest < 0
    OR normalized_search_interest > 400
