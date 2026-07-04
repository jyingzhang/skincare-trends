/*
Purpose: Pull skincare product data from Sephora
*/

SELECT   
    product_id,
    product_name,
    primary_category,
    secondary_category,
    brand_name,
    reviews,
    size,
    ingredients,
    price_usd
FROM {{ source('raw', 'raw_sephora_products') }}
WHERE primary_category = 'Skincare'