{{ config_partitioned_trends(cluster_by=['ingredient_name', 'tag_name']) }}

/*
Purpose: Ingredient trends exploded by purpose and benefit tags for Looker breakdowns.
Grain: date x ingredient x tag (benefit rows duplicate per purpose_tag_name when an
  ingredient maps to multiple purposes)
Notes:
  tag_type = 'purpose'  → split from commonly_known_as (AHA, Vitamin C, Antioxidant, …)
  tag_type = 'benefit'  → split from benefits (Hydrating, Acne Fighter, …)
  purpose_tag_name    → use for purpose dropdown / cross-filters on BOTH purpose and
                        benefit charts (not tag_name, which differs by tag_type)
  search_interest is each ingredient's own 0-100 scale; do not AVG across ingredients
  within a tag and treat the result as category-level search volume.
  Ingredient WoW fields are per ingredient. Tag WoW fields aggregate AVG(search_interest)
  within tag x date first, then compute period-over-period change — use tag_* WoW in
  purpose/benefit pivot tables (do not AVG wow_search_interest_pct_change).
*/

WITH purpose_tags AS (
    SELECT
        ingredient_name,
        alias_term AS tag_name,
        'purpose' AS tag_type
    FROM {{ ref('int_top_used_ingredient_aliases') }}
    WHERE alias_source = 'commonly_known_as'
),

benefit_tags AS (
    SELECT
        ingredient_name,
        benefit_name AS tag_name,
        'benefit' AS tag_type
    FROM {{ ref('int_top_used_ingredient_benefits') }}
),

ingredient_purposes AS (
    SELECT
        ingredient_name,
        alias_term AS purpose_tag_name
    FROM {{ ref('int_top_used_ingredient_aliases') }}
    WHERE alias_source = 'commonly_known_as'
),

tags AS (
    SELECT * FROM purpose_tags
    UNION ALL
    SELECT * FROM benefit_tags
),

base AS (
    SELECT
        t.date,
        t.ingredient_name,
        t.ingredient_name_raw,
        t.search_keyword,
        tag.tag_type,
        tag.tag_name,
        tc.catalog_product_count,
        tc.pilot_product_count,
        tc.trends_tracked_product_count,
        t.product_count AS ingredient_catalog_product_count,
        t.pilot_product_count AS ingredient_pilot_product_count,
        t.trends_tracked_product_count AS ingredient_trends_tracked_product_count,
        t.is_in_catalog,
        t.is_in_pilot_cohort,
        t.is_in_product_trends,
        t.active_weeks,
        t.has_reliable_signal,
        t.is_weekly_peak,
        t.search_interest_raw,
        t.search_interest,
        w.previous_snapshot_date,
        w.previous_search_interest,
        w.wow_search_interest_delta,
        ROUND(
            w.wow_search_interest_delta / NULLIF(w.previous_search_interest, 0),
            4
        ) AS wow_search_interest_pct_change
    FROM {{ ref('fct_ingredients_trends') }} AS t
    INNER JOIN tags AS tag
        ON t.ingredient_name = tag.ingredient_name
    INNER JOIN {{ ref('int_tag_product_counts') }} AS tc
        ON tag.tag_name = tc.tag_name
        AND tag.tag_type = tc.tag_type
    LEFT JOIN {{ ref('int_ingredient_trends_wow') }} AS w
        ON t.date = w.snapshot_date
        AND t.ingredient_name = w.ingredient_name
),

tag_weekly AS (
    SELECT
        tag_name,
        tag_type,
        date,
        AVG(search_interest) AS tag_avg_search_interest
    FROM (
        SELECT DISTINCT
            tag_name,
            tag_type,
            date,
            ingredient_name,
            search_interest
        FROM base
    )
    GROUP BY ALL
),

tag_wow AS (
    SELECT
        tag_name,
        tag_type,
        date,
        tag_avg_search_interest,
        LAG(date) OVER (
            PARTITION BY tag_name, tag_type
            ORDER BY date
        ) AS tag_previous_snapshot_date,
        LAG(tag_avg_search_interest) OVER (
            PARTITION BY tag_name, tag_type
            ORDER BY date
        ) AS tag_previous_search_interest
    FROM tag_weekly
),

tag_wow_metrics AS (
    SELECT
        tag_name,
        tag_type,
        date,
        tag_avg_search_interest,
        tag_previous_snapshot_date,
        tag_previous_search_interest,
        tag_avg_search_interest - tag_previous_search_interest AS tag_wow_search_interest_delta,
        ROUND(
            (tag_avg_search_interest - tag_previous_search_interest)
            / NULLIF(tag_previous_search_interest, 0),
            4
        ) AS tag_wow_search_interest_pct_change
    FROM tag_wow
),

purpose_rows AS (
    SELECT
        b.*,
        b.tag_name AS purpose_tag_name
    FROM base AS b
    WHERE b.tag_type = 'purpose'
),

benefit_rows AS (
    SELECT
        b.*,
        ip.purpose_tag_name
    FROM base AS b
    INNER JOIN ingredient_purposes AS ip
        ON b.ingredient_name = ip.ingredient_name
    WHERE b.tag_type = 'benefit'
),

expanded AS (
    SELECT * FROM purpose_rows
    UNION ALL
    SELECT * FROM benefit_rows
)

SELECT
    e.*,
    tw.tag_avg_search_interest,
    tw.tag_previous_snapshot_date,
    tw.tag_previous_search_interest,
    tw.tag_wow_search_interest_delta,
    tw.tag_wow_search_interest_pct_change
FROM expanded AS e
LEFT JOIN tag_wow_metrics AS tw
    ON e.tag_name = tw.tag_name
    AND e.tag_type = tw.tag_type
    AND e.date = tw.date
