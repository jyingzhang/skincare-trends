{{ config_partitioned_trends(cluster_by=['ingredient_name']) }}

/*
Purpose: Per-ingredient Google Trends interest (anchorless / self-scaled).
Grain: date x ingredient_name
Notes (anchorless / self-scaled):
  Each ingredient is fetched on its own 0-100 Google Trends scale (no shared anchor),
  so the raw value already IS the normalized signal; normalized == raw. This preserves
  low-volume ingredients that a dominant anchor (e.g. "retinol") would floor to 0, at
  the cost of cross-ingredient absolute comparability. Correlation analysis is
  scale-invariant, so self-scaled series are ideal for ingredient<->product correlation.
*/

WITH base AS (
    SELECT
        {{ cast_trend_date('date') }} AS date,
        {{ clean_ingredient_name('ingredient_name') }} AS ingredient_name,
        search_interest,
        is_anchor
    FROM {{ source('raw', 'raw_trends') }}
    WHERE NULLIF(TRIM(ingredient_name), '') IS NOT NULL
)

SELECT
    date,
    ingredient_name,
    search_interest AS raw_search_interest,
    CAST(search_interest AS FLOAT64) AS normalized_search_interest
FROM base
WHERE is_anchor = false
