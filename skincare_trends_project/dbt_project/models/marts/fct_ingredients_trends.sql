{{ config_partitioned_trends(cluster_by=['ingredient_name']) }}

/*
Purpose: Ingredient-level Google Trends mart for the seeded top-ingredient cohort.
Grain: date x ingredient
Notes (anchorless / self-scaled):
  search_interest is each ingredient's own 0-100 scale (100 = its 12-month peak).
  active_weeks + has_reliable_signal separate sustained interest from one-week
  noise spikes; is_weekly_peak flags an ingredient at/near its 12-month high.
*/

{% set reliable_min_weeks = 13 %}
{% set peak_threshold = 90 %}

WITH signal AS (
    SELECT
        ingredient_name,
        COUNTIF(raw_search_interest > 0) AS active_weeks
    FROM {{ ref('int_ingredient_trends_normalized') }}
    GROUP BY ingredient_name
)

SELECT
    t.date,
    s.ingredient_name,
    s.ingredient_name_raw,
    s.search_keyword,
    s.benefits_raw AS benefits,
    s.commonly_known_as_raw AS commonly_known_as,
    s.product_count,
    s.pilot_product_count,
    s.trends_tracked_product_count,
    s.product_count > 0 AS is_in_catalog,
    s.pilot_product_count > 0 AS is_in_pilot_cohort,
    s.trends_tracked_product_count > 0 AS is_in_product_trends,
    sig.active_weeks,
    sig.active_weeks >= {{ reliable_min_weeks }} AS has_reliable_signal,
    t.normalized_search_interest >= {{ peak_threshold }} AS is_weekly_peak,
    t.raw_search_interest AS search_interest_raw,
    t.normalized_search_interest AS search_interest
FROM {{ ref('int_ingredient_trends_normalized') }} AS t
INNER JOIN {{ ref('int_ingredient_trends_cohort') }} AS s
    ON t.ingredient_name = s.ingredient_name
INNER JOIN signal AS sig
    ON t.ingredient_name = sig.ingredient_name
