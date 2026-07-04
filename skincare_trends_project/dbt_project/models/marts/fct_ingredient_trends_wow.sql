{{ config_partitioned_trends(cluster_by=['ingredient_name'], partition_field='snapshot_date') }}

/*
Purpose: Ingredient WoW mart with display attributes and pct change.
Grain: snapshot_date x ingredient
Notes (anchorless / self-scaled):
  current/previous_search_interest are each ingredient's own 0-100 scale.
  active_weeks + has_reliable_signal let "Top Movers" exclude one-week noise;
  is_weekly_peak flags the current snapshot at/near its 12-month high.
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
    w.snapshot_date,
    s.ingredient_name,
    s.ingredient_name_raw,
    s.search_keyword,
    s.benefits_raw AS benefits,
    s.commonly_known_as_raw AS commonly_known_as,
    s.ingredient_definition,
    s.product_count,
    s.pilot_product_count,
    s.trends_tracked_product_count,
    s.product_count > 0 AS is_in_catalog,
    s.pilot_product_count > 0 AS is_in_pilot_cohort,
    s.trends_tracked_product_count > 0 AS is_in_product_trends,
    sig.active_weeks,
    sig.active_weeks >= {{ reliable_min_weeks }} AS has_reliable_signal,
    w.current_search_interest >= {{ peak_threshold }} AS is_weekly_peak,
    w.previous_snapshot_date,
    w.current_search_interest,
    w.previous_search_interest,
    w.wow_search_interest_delta,
    ROUND(
        w.wow_search_interest_delta / NULLIF(w.previous_search_interest, 0),
        4
    ) AS wow_search_interest_pct_change
FROM {{ ref('int_ingredient_trends_wow') }} AS w
INNER JOIN {{ ref('int_ingredient_trends_cohort') }} AS s
    ON w.ingredient_name = s.ingredient_name
INNER JOIN signal AS sig
    ON w.ingredient_name = sig.ingredient_name
