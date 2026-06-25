from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CLIENTS_PATH = ROOT / "config" / "clients.json"


@dataclass
class DbCredentials:
    client: str
    username: str
    password: str


def load_clients(path: Path = CLIENTS_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _connect(credentials: DbCredentials):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Chua co PostgreSQL driver. Hay chay install_deps.bat mot lan roi mo lai tool."
        ) from exc

    clients = load_clients()
    if credentials.client not in clients:
        raise ValueError(f"Client khong hop le: {credentials.client}")
    info = clients[credentials.client]
    return psycopg.connect(
        host=info["host"],
        port=info["port"],
        dbname=info["database"],
        user=credentials.username,
        password=credentials.password,
        connect_timeout=20,
    )


def _table_columns(conn, table_name: str) -> set[str]:
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
    """
    with conn.cursor() as cursor:
        cursor.execute(query, (table_name,))
        return {row[0] for row in cursor.fetchall()}


def _seller_expr_for_table(conn, table_name: str, fallback_id_col: str | None = None) -> str:
    columns = _table_columns(conn, table_name)
    for direct_col in ("seller", "seller_id", "seller_used_id", "used_id"):
        if direct_col in columns:
            return direct_col
    if "fk_seller_used_id" in columns:
        return """
            CONCAT(
                split_part(fk_seller_used_id, '.', 1), '.',
                split_part(fk_seller_used_id, '.', 2), '.',
                split_part(fk_seller_used_id, '.', 3)
            )
        """
    if fallback_id_col is None:
        for candidate in ("fk_sku_used_id", "fk_seller_used_id", "used_id"):
            if candidate in columns:
                fallback_id_col = candidate
                break
    if fallback_id_col is None:
        raise ValueError(f"Khong tim thay seller key trong table {table_name}. Columns: {sorted(columns)}")
    return f"""
        CONCAT(
            split_part({fallback_id_col}, '.', 1), '.',
            split_part({fallback_id_col}, '.', 2), '.',
            split_part({fallback_id_col}, '.', 3)
        )
    """


QUERY_DEFINITIONS = {
    "seller_sales": {
        "sql": """
            SELECT
                __SELLER_EXPR__ AS seller_id,
                day::date AS day,
                COALESCE(source, 'NULL_SOURCE') AS source,
                SUM(quantity) AS quantity,
                SUM(revenue) AS revenue,
                NULL::numeric AS page_view
            FROM ecommerce_export_seller_sales
            WHERE day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND __SELLER_EXPR__ = %(seller_id)s
            GROUP BY 1, 2, 3
        """,
        "level": "seller",
        "table": "ecommerce_export_seller_sales",
        "fallback_id_col": "fk_seller_used_id",
    },
    "item_seller_sales": {
        "sql": """
            SELECT
                %(seller_id)s AS seller_id,
                ei.day::date AS day,
                COALESCE(ei.source, 'NULL_SOURCE') AS source,
                SUM(ei.quantity) AS quantity,
                SUM(
                    CASE
                        WHEN split_part(COALESCE(ei.seller_used_id, sel.used_id), '.', 2) = 'LAZ' THEN ei.s_net
                        WHEN split_part(COALESCE(ei.seller_used_id, sel.used_id), '.', 2) IN ('SHP', 'TTK') THEN ei.s_paid
                        ELSE COALESCE(ei.s_paid, ei.s_net, ei.s_onsite_selling, ei.s_seller_selling, 0)
                    END
                ) AS revenue,
                NULL::numeric AS page_view
            FROM ecommerce_item ei
            LEFT JOIN ecommerce_sku sku
                ON ei.fk_sku_used_id = sku.used_id
            LEFT JOIN ecommerce_seller sel
                ON sku.fk_seller_id = sel.id
            WHERE ei.day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND (
                    ei.seller_used_id = %(seller_id)s
                    OR sel.used_id = %(seller_id)s
                    OR CONCAT(
                        split_part(ei.fk_sku_used_id, '.', 1), '.',
                        split_part(ei.fk_sku_used_id, '.', 2), '.',
                        split_part(ei.fk_sku_used_id, '.', 3)
                    ) = %(seller_id)s
                    OR ei.fk_sku_used_id LIKE %(seller_id_like)s
              )
            GROUP BY 1, 2, 3
        """,
        "level": "seller",
        "as_data_type": "seller_sales",
        "table": "ecommerce_item",
        "fallback_id_col": "fk_sku_used_id",
    },
    "seller_traffic": {
        "sql": """
            SELECT
                __SELLER_EXPR__ AS seller_id,
                day::date AS day,
                COALESCE(source, 'NULL_SOURCE') AS source,
                NULL::numeric AS quantity,
                NULL::numeric AS revenue,
                SUM(page_view) AS page_view
            FROM ecommerce_export_seller_traffic
            WHERE day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND __SELLER_EXPR__ = %(seller_id)s
            GROUP BY 1, 2, 3
        """,
        "level": "seller",
        "table": "ecommerce_export_seller_traffic",
        "fallback_id_col": "fk_seller_used_id",
    },
    "sku_sales": {
        "sql": """
            SELECT
                %(seller_id)s AS seller_id,
                ei.day::date AS day,
                COALESCE(ei.source, 'NULL_SOURCE') AS source,
                SUM(ei.quantity) AS quantity,
                SUM(ei.s_onsite_selling) AS revenue,
                NULL::numeric AS page_view
            FROM ecommerce_export_sku_sales ei
            LEFT JOIN ecommerce_sku sku
                ON ei.fk_sku_used_id = sku.used_id
            LEFT JOIN ecommerce_seller sel
                ON sku.fk_seller_id = sel.id
            WHERE ei.day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND (
                    sel.used_id = %(seller_id)s
                    OR CONCAT(
                        split_part(ei.fk_sku_used_id, '.', 1), '.',
                        split_part(ei.fk_sku_used_id, '.', 2), '.',
                        split_part(ei.fk_sku_used_id, '.', 3)
                    ) = %(seller_id)s
                    OR ei.fk_sku_used_id LIKE %(seller_id_like)s
              )
            GROUP BY 1, 2, 3
        """,
        "level": "sku",
        "table": "ecommerce_export_sku_sales",
        "fallback_id_col": "fk_sku_used_id",
    },
    "item_sku_sales": {
        "sql": """
            SELECT
                %(seller_id)s AS seller_id,
                ei.day::date AS day,
                COALESCE(ei.source, 'NULL_SOURCE') AS source,
                SUM(ei.quantity) AS quantity,
                SUM(
                    CASE
                        WHEN split_part(COALESCE(ei.seller_used_id, sel.used_id), '.', 2) = 'LAZ' THEN ei.s_net
                        WHEN split_part(COALESCE(ei.seller_used_id, sel.used_id), '.', 2) IN ('SHP', 'TTK') THEN ei.s_paid
                        ELSE COALESCE(ei.s_paid, ei.s_net, ei.s_onsite_selling, ei.s_seller_selling, 0)
                    END
                ) AS revenue,
                NULL::numeric AS page_view
            FROM ecommerce_item ei
            LEFT JOIN ecommerce_sku sku
                ON ei.fk_sku_used_id = sku.used_id
            LEFT JOIN ecommerce_seller sel
                ON sku.fk_seller_id = sel.id
            WHERE ei.day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND (
                    ei.seller_used_id = %(seller_id)s
                    OR sel.used_id = %(seller_id)s
                    OR CONCAT(
                        split_part(ei.fk_sku_used_id, '.', 1), '.',
                        split_part(ei.fk_sku_used_id, '.', 2), '.',
                        split_part(ei.fk_sku_used_id, '.', 3)
                    ) = %(seller_id)s
                    OR ei.fk_sku_used_id LIKE %(seller_id_like)s
              )
            GROUP BY 1, 2, 3
        """,
        "level": "sku",
        "as_data_type": "sku_sales",
        "table": "ecommerce_item",
        "fallback_id_col": "fk_sku_used_id",
    },
    "sku_traffic": {
        "sql": """
            SELECT
                %(seller_id)s AS seller_id,
                ei.day::date AS day,
                COALESCE(ei.source, 'NULL_SOURCE') AS source,
                NULL::numeric AS quantity,
                NULL::numeric AS revenue,
                SUM(ei.page_view) AS page_view
            FROM ecommerce_export_sku_traffic ei
            LEFT JOIN ecommerce_sku sku
                ON ei.fk_sku_used_id = sku.used_id
            LEFT JOIN ecommerce_seller sel
                ON sku.fk_seller_id = sel.id
            WHERE ei.day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND (
                    sel.used_id = %(seller_id)s
                    OR CONCAT(
                        split_part(ei.fk_sku_used_id, '.', 1), '.',
                        split_part(ei.fk_sku_used_id, '.', 2), '.',
                        split_part(ei.fk_sku_used_id, '.', 3)
                    ) = %(seller_id)s
                    OR ei.fk_sku_used_id LIKE %(seller_id_like)s
              )
            GROUP BY 1, 2, 3
        """,
        "level": "sku",
        "table": "ecommerce_export_sku_traffic",
        "fallback_id_col": "fk_sku_used_id",
    },
}


def query_seller_sources(
    credentials: DbCredentials,
    seller_id: str,
    start_date: str,
    end_date: str,
    data_level: str = "both",
    use_item_sales: bool = False,
) -> pd.DataFrame:
    df, _ = query_seller_sources_with_debug(credentials, seller_id, start_date, end_date, data_level, use_item_sales)
    return df


def query_seller_sources_with_debug(
    credentials: DbCredentials,
    seller_id: str,
    start_date: str,
    end_date: str,
    data_level: str = "both",
    use_item_sales: bool = False,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    params = {"seller_id": seller_id, "seller_id_like": f"{seller_id}.%", "start_date": start_date, "end_date": end_date}
    frames: list[pd.DataFrame] = []
    debug_rows: list[dict[str, Any]] = []
    wanted_level = (data_level or "both").lower()
    with _connect(credentials) as conn:
        for data_type, definition in QUERY_DEFINITIONS.items():
            if use_item_sales and data_type in ("seller_sales", "sku_sales"):
                continue
            if not use_item_sales and data_type in ("item_seller_sales", "item_sku_sales"):
                continue
            if wanted_level in ("seller", "sku") and definition["level"] != wanted_level:
                continue
            sql = definition["sql"]
            if "__SELLER_EXPR__" in sql:
                seller_expr = _seller_expr_for_table(conn, definition["table"], definition["fallback_id_col"])
                sql = sql.replace("__SELLER_EXPR__", seller_expr)
            debug_row = {
                "seller_id": seller_id,
                "query_source_table": data_type,
                "physical_table": definition["table"],
                "data_level": definition["level"],
                "data_type": definition.get("as_data_type", data_type),
                "use_item_sales": use_item_sales,
                "start_date": start_date,
                "end_date": end_date,
                "row_count": 0,
                "quantity_sum": 0,
                "revenue_sum": 0,
                "page_view_sum": 0,
                "first_day": "",
                "last_day": "",
                "source_sample": "",
                "status": "ok",
                "error": "",
            }
            try:
                df = pd.read_sql_query(sql, conn, params=params)
            except Exception as exc:
                debug_row["status"] = "error"
                debug_row["error"] = str(exc)
                debug_rows.append(debug_row)
                continue
            debug_row["row_count"] = int(len(df))
            if not df.empty:
                for metric, debug_key in (("quantity", "quantity_sum"), ("revenue", "revenue_sum"), ("page_view", "page_view_sum")):
                    if metric in df.columns:
                        debug_row[debug_key] = float(pd.to_numeric(df[metric], errors="coerce").fillna(0).sum())
                if "day" in df.columns:
                    days = pd.to_datetime(df["day"], errors="coerce").dropna()
                    if not days.empty:
                        debug_row["first_day"] = str(days.min().date())
                        debug_row["last_day"] = str(days.max().date())
                if "source" in df.columns:
                    debug_row["source_sample"] = ", ".join([str(item) for item in df["source"].dropna().astype(str).unique()[:5]])
            debug_rows.append(debug_row)
            if df.empty:
                continue
            df.insert(0, "data_type", definition.get("as_data_type", data_type))
            df.insert(1, "data_level", definition["level"])
            df.insert(2, "query_source_table", data_type)
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["data_type", "data_level", "query_source_table", "seller_id", "day", "source", "quantity", "revenue", "page_view"]), debug_rows
    return pd.concat(frames, ignore_index=True), debug_rows
