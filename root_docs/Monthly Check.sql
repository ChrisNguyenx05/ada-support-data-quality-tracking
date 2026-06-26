-- Monthly by selected month, seller_id, and source
WITH params AS (
    SELECT
        DATE '2026-05-01' AS target_month,
        ARRAY[
            'PH.TTK.7494652724024937219'
        ]::text[] AS seller_ids,
        ARRAY[
           'item',
            'export_sku_sale',
           'export_sku_traffic'
        ]::text[] AS sources,
        'loreal_group_ph'::text AS company
),
item_fact AS (
    SELECT
        p.company  AS company,
        split_part(es.used_id, '.', 1) AS country,
        split_part(es.used_id, '.', 2) AS marketplace,
        es.used_id AS seller_id,
        DATE_TRUNC('month', ei.day)::date AS year_month,
        'item' AS source,
        NULL AS mapping_check,
        NULL AS has_finace,
        NULL AS component_number,
        NULL AS cancel_not_cancel,
        SUM(ei.quantity) AS sum_quantity,
        SUM(
            CASE
                WHEN ei.day >= DATE '2026-01-22'
                     AND split_part(es.used_id, '.', 2) IN ('SHP','LAZ')
                    THEN ei.s_net
                WHEN ei.day >= DATE '2026-01-22'
                     AND split_part(es.used_id, '.', 2) = 'TTK'
                    THEN ei.s_paid
                WHEN ei.day < DATE '2026-01-22'
                     AND split_part(es.used_id, '.', 2) = 'LAZ'
                    THEN ei.s_net
                WHEN ei.day < DATE '2026-01-22'
                     AND split_part(es.used_id, '.', 2) IN ('SHP','TTK')
                    THEN ei.s_paid
                ELSE 0
            END
        ) AS sum_revenue,
        NULL::bigint AS page_view,
        current_timestamp AS query_date,
        NULL AS product_impression
    FROM ecommerce_item ei
    JOIN ecommerce_seller es
        ON ei.seller_used_id = es.used_id
    CROSS JOIN params p
    WHERE ei.day >= p.target_month
      AND ei.day <  p.target_month + INTERVAL '1 month'
      AND es.used_id = ANY(p.seller_ids)
      AND 'item' = ANY(p.sources)
    GROUP BY
        1,2,3,4,5
),
sku_sale_base AS (
    SELECT
        eess.*,
        COALESCE(
            sel.used_id,
            CONCAT(
                split_part(eess.fk_sku_used_id,'.',1), '.',
                split_part(eess.fk_sku_used_id,'.',2), '.',
                split_part(eess.fk_sku_used_id,'.',3)
            )
        ) AS resolved_seller_id
    FROM ecommerce_export_sku_sales eess
    LEFT JOIN ecommerce_sku sku
        ON eess.fk_sku_used_id = sku.used_id
    LEFT JOIN ecommerce_seller sel
        ON sku.fk_seller_id = sel.id
),
sku_sale_fact AS (
    SELECT
        p.company AS company,
        split_part(ss.resolved_seller_id, '.', 1) AS country,
        split_part(ss.resolved_seller_id, '.', 2) AS marketplace,
        ss.resolved_seller_id AS seller_id,
        DATE_TRUNC('month', ss.day)::date AS year_month,
        'export_sku_sale' AS source,
        NULL AS mapping_check,
        NULL AS has_finace,
        NULL AS component_number,
        NULL AS cancel_not_cancel,
        SUM(ss.quantity) AS sum_quantity,
        SUM(ss.s_onsite_selling) AS sum_revenue,
        NULL::bigint AS page_view,
        current_timestamp AS query_date,
        NULL AS product_impression
    FROM sku_sale_base ss
    CROSS JOIN params p
    WHERE ss.day >= p.target_month
      AND ss.day <  p.target_month + INTERVAL '1 month'
      AND ss.resolved_seller_id = ANY(p.seller_ids)
      AND 'export_sku_sale' = ANY(p.sources)
    GROUP BY
        1,2,3,4,5
),
sku_traffic_base AS (
    SELECT
        eest.*,
        COALESCE(
            sel.used_id,
            CONCAT(
                split_part(eest.fk_sku_used_id,'.',1), '.',
                split_part(eest.fk_sku_used_id,'.',2), '.',
                split_part(eest.fk_sku_used_id,'.',3)
            )
        ) AS resolved_seller_id
    FROM ecommerce_export_sku_traffic eest
    LEFT JOIN ecommerce_sku sku
        ON eest.fk_sku_used_id = sku.used_id
    LEFT JOIN ecommerce_seller sel
        ON sku.fk_seller_id = sel.id
),
sku_traffic_fact AS (
    SELECT
        p.company AS company,
        split_part(st.resolved_seller_id, '.', 1) AS country,
        split_part(st.resolved_seller_id, '.', 2) AS marketplace,
        st.resolved_seller_id AS seller_id,
        DATE_TRUNC('month', st.day)::date AS year_month,
        'export_sku_traffic' AS source,
        NULL AS mapping_check,
        NULL AS has_finace,
        NULL AS component_number,
        NULL AS cancel_not_cancel,
        NULL::bigint AS sum_quantity,
        NULL::numeric AS sum_revenue,
        SUM(st.page_view) AS page_view,
        current_timestamp AS query_date,
        NULL AS product_impression
    FROM sku_traffic_base st
    CROSS JOIN params p
    WHERE st.day >= p.target_month
      AND st.day <  p.target_month + INTERVAL '1 month'
      AND st.resolved_seller_id = ANY(p.seller_ids)
      AND 'export_sku_traffic' = ANY(p.sources)
    GROUP BY
        1,2,3,4,5
)
SELECT *
FROM item_fact
UNION ALL
SELECT s.*
FROM sku_sale_fact s
WHERE NOT EXISTS (
    SELECT 1
    FROM item_fact i
    WHERE i.company     = s.company
      AND i.country     = s.country
      AND i.marketplace = s.marketplace
      AND i.seller_id   = s.seller_id
      AND i.year_month  = s.year_month
)
UNION ALL
SELECT *
FROM sku_traffic_fact;
