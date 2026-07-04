/*
Purpose: Ingredient reference dictionary for Looker / Data Studio glossary pages.
Grain: ingredient_name
Notes:
  Join to trend marts on ingredient_name for tooltips and detail panels.
  benefits and commonly_known_as are comma-separated display labels from the seed.
*/

SELECT
    s.ingredient_name,
    s.ingredient_name_raw,
    s.benefits_raw AS benefits,
    s.commonly_known_as_raw AS commonly_known_as,
    s.ingredient_definition,
    s.product_count,
    pc.pilot_product_count,
    pc.trends_tracked_product_count
FROM {{ ref('int_top_used_ingredients_seed') }} AS s
LEFT JOIN {{ ref('int_ingredient_product_counts') }} AS pc
    ON s.ingredient_name = pc.ingredient_name
