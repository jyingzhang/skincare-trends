-- Fail if mart grain is not unique: date x product_id
SELECT
    date,
    product_id,
    COUNT(*) AS row_count
FROM {{ ref('fct_product_trends') }}
GROUP BY 1, 2
HAVING COUNT(*) > 1
