{{ config_partitioned_trends(cluster_by=['product_id']) }}

/*
Purpose: Per-product Google Trends interest (anchorless / self-scaled).
Grain: date x product_id
Notes:
  Each product is fetched on its own 0-100 Google Trends scale (no shared anchor),
  so the raw value already IS the normalized signal. We keep both columns for
  schema stability; normalized_search_interest == raw_search_interest.
  This preserves low-volume products that a dominant anchor would floor to 0,
  at the cost of cross-product absolute comparability.
*/

SELECT
    {{ cast_trend_date('date') }} AS date,
    product_id,
    search_keyword,
    search_interest AS raw_search_interest,
    CAST(search_interest AS FLOAT64) AS normalized_search_interest
FROM {{ source('raw', 'raw_product_trends') }}
WHERE is_anchor = false
    AND product_id IS NOT NULL
