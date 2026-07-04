{{ config_partitioned_trends(cluster_by=['product_id'], partition_field='snapshot_date') }}

/*
Purpose: Pilot product WoW mart with display attributes and pct change.
Grain: snapshot_date x product
Notes (anchorless / self-scaled):
  - current/previous_search_interest are each product's own 0-100 scale.
  - active_weeks + has_reliable_signal let "Top Movers" exclude one-week noise
    spikes; is_weekly_peak flags the current snapshot at/near its 12-month high.
*/

{% set reliable_min_weeks = 13 %}
{% set peak_threshold = 90 %}

WITH signal AS (
    SELECT
        product_id,
        COUNTIF(raw_search_interest > 0) AS active_weeks
    FROM {{ ref('int_product_trends_normalized') }}
    GROUP BY product_id
)

SELECT
    w.snapshot_date,
    p.product_id,
    p.product_name,
    p.brand_name,
    p.primary_category,
    p.secondary_category,
    p.search_keyword,
    p.probed_search_keyword,
    p.total_reviews,
    p.review_count_rank,
    p.stability_rank,
    p.has_probe_signal,
    s.active_weeks,
    s.active_weeks >= {{ reliable_min_weeks }} AS has_reliable_signal,
    w.current_search_interest >= {{ peak_threshold }} AS is_weekly_peak,
    w.previous_snapshot_date,
    w.current_search_interest,
    w.previous_search_interest,
    w.wow_search_interest_delta,
    ROUND(
        w.wow_search_interest_delta / NULLIF(w.previous_search_interest, 0),
        4
    ) AS wow_search_interest_pct_change
FROM {{ ref('int_product_trends_wow') }} AS w
INNER JOIN {{ ref('int_pilot_products') }} AS p
    ON w.product_id = p.product_id
INNER JOIN signal AS s
    ON w.product_id = s.product_id
