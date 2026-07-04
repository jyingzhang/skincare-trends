-- Fail if mart grain is not unique: snapshot_date x ingredient_name
SELECT
    snapshot_date,
    ingredient_name,
    COUNT(*) AS row_count
FROM {{ ref('fct_ingredient_trends_wow') }}
GROUP BY 1, 2
HAVING COUNT(*) > 1
