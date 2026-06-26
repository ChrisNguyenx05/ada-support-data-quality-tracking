-- Monthly audit by month, seller_id, and source
WITH params AS (
    SELECT
        DATE '2026-05-01' AS target_month,
        ARRAY[
            'PH.SHP.76176908'
        ]::text[] AS seller_ids,
        ARRAY[
            'item',
            'export_seller_sales',
            'export_seller_traffic',
            'export_sku_sale',
            'export_sku_traffic'
        ]::text[] AS sources,
        'nestle_purina'::text AS company
),

item_sales AS (
    SELECT
        CONCAT(p.company, ' - ', es.used_id) AS "company - seller",
        p.company AS company,
        split_part(es.used_id, '.', 1) AS country,
        split_part(es.used_id, '.', 2) AS marketplace,
        es.used_id AS seller_id,
        DATE_TRUNC('month', ei.day)::date AS year_month,
        'item' AS source,
        NULL::text AS mapping_check,
        NULL::text AS has_finace,
        NULL::text AS component_number,
        NULL::text AS cancel_not_cancel,
        SUM(ei.quantity)::bigint AS sum_quantity,
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
        )::numeric AS sum_revenue,
        NULL::bigint AS page_view,
        current_timestamp AS query_date,
        NULL::bigint AS product_impression
    FROM ecommerce_item ei
    JOIN ecommerce_seller es
        ON ei.seller_used_id = es.used_id
    CROSS JOIN params p
    WHERE ei.day >= p.target_month
      AND ei.day <  p.target_month + INTERVAL '1 month'
      AND es.used_id = ANY(p.seller_ids)
      AND 'item' = ANY(p.sources)
    GROUP BY p.company, es.used_id, DATE_TRUNC('month', ei.day)
),

seller_sales AS (
    SELECT
        CONCAT(p.company, ' - ', eess.fk_seller_used_id) AS "company - seller",
        p.company AS company,
        split_part(eess.fk_seller_used_id, '.', 1) AS country,
        split_part(eess.fk_seller_used_id, '.', 2) AS marketplace,
        eess.fk_seller_used_id AS seller_id,
        DATE_TRUNC('month', eess.day)::date AS year_month,
        'export_seller_sales' AS source,
        NULL::text AS mapping_check,
        NULL::text AS has_finace,
        NULL::text AS component_number,
        NULL::text AS cancel_not_cancel,
        SUM(eess.quantity)::bigint AS sum_quantity,
        SUM(eess.revenue)::numeric AS sum_revenue,
        NULL::bigint AS page_view,
        current_timestamp AS query_date,
        SUM(eess.product_impression)::bigint AS product_impression
    FROM ecommerce_export_seller_sales eess
    CROSS JOIN params p
    WHERE eess.day >= p.target_month
      AND eess.day <  p.target_month + INTERVAL '1 month'
      AND eess.fk_seller_used_id = ANY(p.seller_ids)
      AND 'export_seller_sales' = ANY(p.sources)
    GROUP BY p.company, eess.fk_seller_used_id, DATE_TRUNC('month', eess.day)
),

seller_traffic AS (
    SELECT
        CONCAT(p.company, ' - ', eest.fk_seller_used_id) AS "company - seller",
        p.company AS company,
        split_part(eest.fk_seller_used_id, '.', 1) AS country,
        split_part(eest.fk_seller_used_id, '.', 2) AS marketplace,
        eest.fk_seller_used_id AS seller_id,
        DATE_TRUNC('month', eest.day)::date AS year_month,
        'export_seller_traffic' AS source,
        NULL::text AS mapping_check,
        NULL::text AS has_finace,
        NULL::text AS component_number,
        NULL::text AS cancel_not_cancel,
        NULL::bigint AS sum_quantity,
        NULL::numeric AS sum_revenue,
        SUM(eest.page_view)::bigint AS page_view,
        current_timestamp AS query_date,
        SUM(eest.product_impression)::bigint AS product_impression
    FROM ecommerce_export_seller_traffic eest
    CROSS JOIN params p
    WHERE eest.day >= p.target_month
      AND eest.day <  p.target_month + INTERVAL '1 month'
      AND eest.fk_seller_used_id = ANY(p.seller_ids)
      AND 'export_seller_traffic' = ANY(p.sources)
    GROUP BY p.company, eest.fk_seller_used_id, DATE_TRUNC('month', eest.day)
),

sku_sales_base AS (
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

sku_sales AS (
    SELECT
        CONCAT(p.company, ' - ', ss.resolved_seller_id) AS "company - seller",
        p.company AS company,
        split_part(ss.resolved_seller_id, '.', 1) AS country,
        split_part(ss.resolved_seller_id, '.', 2) AS marketplace,
        ss.resolved_seller_id AS seller_id,
        DATE_TRUNC('month', ss.day)::date AS year_month,
        'export_sku_sale' AS source,
        NULL::text AS mapping_check,
        NULL::text AS has_finace,
        NULL::text AS component_number,
        NULL::text AS cancel_not_cancel,
        SUM(ss.quantity)::bigint AS sum_quantity,
        SUM(ss.s_onsite_selling)::numeric AS sum_revenue,
        NULL::bigint AS page_view,
        current_timestamp AS query_date,
        NULL::bigint AS product_impression
    FROM sku_sales_base ss
    CROSS JOIN params p
    WHERE ss.day >= p.target_month
      AND ss.day <  p.target_month + INTERVAL '1 month'
      AND ss.resolved_seller_id = ANY(p.seller_ids)
      AND 'export_sku_sale' = ANY(p.sources)
    GROUP BY p.company, ss.resolved_seller_id, DATE_TRUNC('month', ss.day)
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

sku_traffic AS (
    SELECT
        CONCAT(p.company, ' - ', st.resolved_seller_id) AS "company - seller",
        p.company AS company,
        split_part(st.resolved_seller_id, '.', 1) AS country,
        split_part(st.resolved_seller_id, '.', 2) AS marketplace,
        st.resolved_seller_id AS seller_id,
        DATE_TRUNC('month', st.day)::date AS year_month,
        'export_sku_traffic' AS source,
        NULL::text AS mapping_check,
        NULL::text AS has_finace,
        NULL::text AS component_number,
        NULL::text AS cancel_not_cancel,
        NULL::bigint AS sum_quantity,
        NULL::numeric AS sum_revenue,
        SUM(st.page_view)::bigint AS page_view,
        current_timestamp AS query_date,
        NULL::bigint AS product_impression
    FROM sku_traffic_base st
    CROSS JOIN params p
    WHERE st.day >= p.target_month
      AND st.day <  p.target_month + INTERVAL '1 month'
      AND st.resolved_seller_id = ANY(p.seller_ids)
      AND 'export_sku_traffic' = ANY(p.sources)
    GROUP BY p.company, st.resolved_seller_id, DATE_TRUNC('month', st.day)
)

SELECT * FROM item_sales
UNION ALL
SELECT * FROM seller_sales
UNION ALL
SELECT * FROM seller_traffic
UNION ALL
SELECT * FROM sku_sales
UNION ALL
SELECT * FROM sku_traffic
ORDER BY
    seller_id,
    year_month,
    source;
