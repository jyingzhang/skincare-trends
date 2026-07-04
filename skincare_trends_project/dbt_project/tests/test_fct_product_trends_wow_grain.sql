-- Fail if mart grain is not unique: snapshot_date x product_id
SELECT
    snapshot_date,
    product_id,
    COUNT(*) AS row_count
FROM {{ ref('fct_product_trends_wow') }}
GROUP BY 1, 2
HAVING COUNT(*) > 1
