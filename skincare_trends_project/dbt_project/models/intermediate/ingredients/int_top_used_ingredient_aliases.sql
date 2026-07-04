/*
Purpose: Normalize ingredient aliases into one row per alias term.
Grain: Ingredient x Alias term
*/

WITH base AS (
    SELECT *
    FROM {{ ref('int_top_used_ingredients_seed') }}
),

canonical_aliases AS (
    SELECT
        ingredient_name,
        ingredient_name AS alias_term,
        'ingredient_name' AS alias_source
    FROM base
),

common_name_aliases AS (
    SELECT
        b.ingredient_name,
        {{ clean_ingredient_name('TRIM(' ~ unnest_col('alias_term_raw') ~ ')') }} AS alias_term,
        'commonly_known_as' AS alias_source
    FROM base AS b
    {{ cross_join_unnest_split("COALESCE(b.commonly_known_as_raw, '')", "','", 'alias_term_raw') }}
    WHERE NULLIF(TRIM({{ unnest_col('alias_term_raw') }}), '') IS NOT NULL
),

all_aliases AS (
    SELECT * FROM canonical_aliases
    UNION ALL
    SELECT * FROM common_name_aliases
)

SELECT
    ingredient_name,
    alias_term,
    alias_source
FROM all_aliases
WHERE NULLIF(TRIM(alias_term), '') IS NOT NULL
GROUP BY ALL
