/*
Purpose: Distinct product counts per purpose/benefit tag.
Grain: tag_name x tag_type

Use trends_tracked_product_count in Looker to align with the ~163 products in fct_product_trends.
*/

WITH pilot_products AS (
    SELECT product_id
    FROM {{ ref('int_pilot_products') }}
),

trends_products AS (
    SELECT DISTINCT product_id
    FROM {{ ref('int_product_trends_normalized') }}
),

purpose_tags AS (
    SELECT DISTINCT
        pi.product_id,
        a.alias_term AS tag_name,
        'purpose' AS tag_type
    FROM {{ ref('int_sephora_product_ingredients') }} AS pi
    INNER JOIN {{ ref('int_top_used_ingredient_aliases') }} AS a
        ON pi.ingredient_name = a.ingredient_name
        AND a.alias_source = 'commonly_known_as'
),

benefit_tags AS (
    SELECT DISTINCT
        pi.product_id,
        b.benefit_name AS tag_name,
        'benefit' AS tag_type
    FROM {{ ref('int_sephora_product_ingredients') }} AS pi
    INNER JOIN {{ ref('int_top_used_ingredient_benefits') }} AS b
        ON pi.ingredient_name = b.ingredient_name
),

tagged_products AS (
    SELECT * FROM purpose_tags
    UNION ALL
    SELECT * FROM benefit_tags
)

SELECT
    t.tag_name,
    t.tag_type,
    COUNT(DISTINCT t.product_id) AS catalog_product_count,
    COUNT(DISTINCT CASE
        WHEN pp.product_id IS NOT NULL THEN t.product_id
    END) AS pilot_product_count,
    COUNT(DISTINCT CASE
        WHEN tr.product_id IS NOT NULL THEN t.product_id
    END) AS trends_tracked_product_count
FROM tagged_products AS t
LEFT JOIN pilot_products AS pp
    ON t.product_id = pp.product_id
LEFT JOIN trends_products AS tr
    ON t.product_id = tr.product_id
GROUP BY ALL
