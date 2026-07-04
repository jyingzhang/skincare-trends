-- Fail if normalized/raw interest falls outside expected bounds.
-- Normalized can exceed 100 when terms outpace the anchor, so we cap at 300.
SELECT *
FROM {{ ref('int_product_trends_normalized') }}
WHERE raw_search_interest < 0
    OR raw_search_interest > 100
    OR normalized_search_interest < 0
    OR normalized_search_interest > 300
