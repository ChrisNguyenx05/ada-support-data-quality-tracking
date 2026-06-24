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


QUERY_DEFINITIONS = {
    "seller_sales": {
        "sql": """
            SELECT
                CONCAT(
                    split_part(fk_seller_used_id, '.', 1), '.',
                    split_part(fk_seller_used_id, '.', 2), '.',
                    split_part(fk_seller_used_id, '.', 3)
                ) AS seller_id,
                day::date AS day,
                COALESCE(source, 'NULL_SOURCE') AS source,
                SUM(quantity) AS quantity,
                SUM(revenue) AS revenue,
                NULL::numeric AS page_view
            FROM ecommerce_export_seller_sales
            WHERE day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND CONCAT(
                    split_part(fk_seller_used_id, '.', 1), '.',
                    split_part(fk_seller_used_id, '.', 2), '.',
                    split_part(fk_seller_used_id, '.', 3)
                  ) = %(seller_id)s
            GROUP BY 1, 2, 3
        """,
        "level": "seller",
    },
    "seller_traffic": {
        "sql": """
            SELECT
                CONCAT(
                    split_part(fk_seller_used_id, '.', 1), '.',
                    split_part(fk_seller_used_id, '.', 2), '.',
                    split_part(fk_seller_used_id, '.', 3)
                ) AS seller_id,
                day::date AS day,
                COALESCE(source, 'NULL_SOURCE') AS source,
                NULL::numeric AS quantity,
                NULL::numeric AS revenue,
                SUM(page_view) AS page_view
            FROM ecommerce_export_seller_traffic
            WHERE day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND CONCAT(
                    split_part(fk_seller_used_id, '.', 1), '.',
                    split_part(fk_seller_used_id, '.', 2), '.',
                    split_part(fk_seller_used_id, '.', 3)
                  ) = %(seller_id)s
            GROUP BY 1, 2, 3
        """,
        "level": "seller",
    },
    "sku_sales": {
        "sql": """
            SELECT
                CONCAT(
                    split_part(fk_sku_used_id, '.', 1), '.',
                    split_part(fk_sku_used_id, '.', 2), '.',
                    split_part(fk_sku_used_id, '.', 3)
                ) AS seller_id,
                day::date AS day,
                COALESCE(source, 'NULL_SOURCE') AS source,
                SUM(quantity) AS quantity,
                SUM(s_onsite_selling) AS revenue,
                NULL::numeric AS page_view
            FROM ecommerce_export_sku_sales
            WHERE day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND CONCAT(
                    split_part(fk_sku_used_id, '.', 1), '.',
                    split_part(fk_sku_used_id, '.', 2), '.',
                    split_part(fk_sku_used_id, '.', 3)
                  ) = %(seller_id)s
            GROUP BY 1, 2, 3
        """,
        "level": "sku",
    },
    "sku_traffic": {
        "sql": """
            SELECT
                CONCAT(
                    split_part(fk_sku_used_id, '.', 1), '.',
                    split_part(fk_sku_used_id, '.', 2), '.',
                    split_part(fk_sku_used_id, '.', 3)
                ) AS seller_id,
                day::date AS day,
                COALESCE(source, 'NULL_SOURCE') AS source,
                NULL::numeric AS quantity,
                NULL::numeric AS revenue,
                SUM(page_view) AS page_view
            FROM ecommerce_export_sku_traffic
            WHERE day BETWEEN %(start_date)s::date AND %(end_date)s::date
              AND CONCAT(
                    split_part(fk_sku_used_id, '.', 1), '.',
                    split_part(fk_sku_used_id, '.', 2), '.',
                    split_part(fk_sku_used_id, '.', 3)
                  ) = %(seller_id)s
            GROUP BY 1, 2, 3
        """,
        "level": "sku",
    },
}


def query_seller_sources(
    credentials: DbCredentials,
    seller_id: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    params = {"seller_id": seller_id, "start_date": start_date, "end_date": end_date}
    frames: list[pd.DataFrame] = []
    with _connect(credentials) as conn:
        for data_type, definition in QUERY_DEFINITIONS.items():
            df = pd.read_sql_query(definition["sql"], conn, params=params)
            if df.empty:
                continue
            df.insert(0, "data_type", data_type)
            df.insert(1, "data_level", definition["level"])
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["data_type", "data_level", "seller_id", "day", "source", "quantity", "revenue", "page_view"])
    return pd.concat(frames, ignore_index=True)
