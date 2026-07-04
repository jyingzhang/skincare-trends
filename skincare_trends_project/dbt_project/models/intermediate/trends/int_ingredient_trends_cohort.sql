/*
Purpose: Google Trends ingredient cohort — top ingredients to track, excluding INCI artifacts.
Grain: ingredient_name

Exclusions:
  - l(+)lacticacid: chiral INCI label form; consumers search "lactic acid", not "l (+) lactic acid".

Disambiguation:
  - Ambiguous ingredients (big non-skincare search volume — e.g. cholesterol/health,
    caffeine/coffee, citric acid/food) get " in skincare" appended to scope the query
    to skincare context. Parentheticals (e.g. "(vitamin c)") are stripped first.
*/

{% set ambiguous_ingredients = [
    'citricacid', 'caffeine', 'lacticacid', 'cholesterol',
    'ascorbicacid', 'ascorbicacid(vitaminc)',
    'malicacid', 'tartaricacid', 'linoleicacid',
    'titaniumdioxide', 'titaniumdioxide(ci77891)',
    'zincoxide', 'adenosine', 'ubiquinone', 'resveratrol',
    'quercetin', 'papain', 'bromelain', 'tranexamicacid', 'tocopherol'
] %}

WITH ranked AS (
    SELECT
        s.ingredient_name,
        s.ingredient_name_raw,
        s.product_count,
        pc.pilot_product_count,
        pc.trends_tracked_product_count,
        s.benefits_raw,
        s.commonly_known_as_raw,
        s.ingredient_definition,
        ROW_NUMBER() OVER (
            ORDER BY s.product_count DESC, s.ingredient_name
        ) AS trend_rank
    FROM {{ ref('int_top_used_ingredients_seed') }} AS s
    INNER JOIN {{ ref('int_ingredient_product_counts') }} AS pc
        ON s.ingredient_name = pc.ingredient_name
    WHERE s.ingredient_name NOT IN (
        'l(+)lacticacid'
    )
)

SELECT
    ingredient_name,
    ingredient_name_raw,
    product_count,
    pilot_product_count,
    trends_tracked_product_count,
    benefits_raw,
    commonly_known_as_raw,
    ingredient_definition,
    CASE
        WHEN ingredient_name IN (
            {%- for ing in ambiguous_ingredients %}
            '{{ ing }}'{% if not loop.last %},{% endif %}
            {%- endfor %}
        )
        THEN TRIM({{ regexp_replace_all('ingredient_name_raw', '\\s*\\([^)]*\\)', '') }}) || ' in skincare'
        ELSE ingredient_name_raw
    END AS search_keyword,
    trend_rank
FROM ranked
WHERE trend_rank <= 100
