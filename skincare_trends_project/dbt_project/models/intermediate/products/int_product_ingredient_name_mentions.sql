/*
Purpose: Flag whether curated ingredients are in product names (name/alias).
Grain: Product x Ingredient
*/

WITH products AS (
    SELECT
        p.product_id,
        p.product_name,
        TRIM({{ regexp_replace_all("LOWER(p.product_name)", '[^a-z0-9]+', ' ') }}) AS product_name_normalized
    FROM {{ ref('stg_sephora_products') }} AS p
),

aliases AS (
    SELECT
        a.ingredient_name,
        a.alias_term,
        a.alias_source,
        TRIM({{ regexp_replace_all("LOWER(a.alias_term)", '[^a-z0-9]+', ' ') }}) AS alias_term_normalized
    FROM {{ ref('int_top_used_ingredient_aliases') }} AS a
),

name_matches AS (
    SELECT
        p.product_id,
        p.product_name,
        a.ingredient_name,
        a.alias_term AS matched_alias_term,
        a.alias_source
    FROM products AS p
    INNER JOIN aliases AS a
        ON LENGTH(a.alias_term_normalized) >= 3
        AND (' ' || p.product_name_normalized || ' ') LIKE ('% ' || a.alias_term_normalized || ' %')
),

ingredient_in_formula AS (
    SELECT
        spi.product_id,
        spi.ingredient_name
    FROM {{ ref('int_sephora_product_ingredients') }} AS spi
    INNER JOIN {{ ref('int_top_used_ingredients_seed') }} AS ti
        ON spi.ingredient_name = ti.ingredient_name
    GROUP BY ALL
),

product_ingredient_pairs AS (
    SELECT product_id, ingredient_name FROM ingredient_in_formula
    UNION DISTINCT
    SELECT product_id, ingredient_name FROM name_matches
)

SELECT
    pi.product_id,
    p.product_name,
    pi.ingredient_name,
    f.product_id IS NOT NULL AS is_ingredient_in_formula,
    COUNT(nm.matched_alias_term) > 0 AS is_ingredient_in_product_name,
    {{ string_agg_distinct('nm.matched_alias_term', "', '") }} AS matched_alias_terms,
    {{ string_agg_distinct('nm.alias_source', "', '") }} AS matched_alias_sources
FROM product_ingredient_pairs AS pi
INNER JOIN products AS p
    ON pi.product_id = p.product_id
LEFT JOIN ingredient_in_formula AS f
    ON pi.product_id = f.product_id
    AND pi.ingredient_name = f.ingredient_name
LEFT JOIN name_matches AS nm
    ON pi.product_id = nm.product_id
    AND pi.ingredient_name = nm.ingredient_name
GROUP BY ALL
