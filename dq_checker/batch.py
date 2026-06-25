from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from dq_checker.core import SellerFileSpec, compare_platform_to_db_sources, read_platform_file
from dq_checker.db import DbCredentials, query_seller_sources_with_debug


def _expected_query_tables_for_specs(specs: list[SellerFileSpec], data_level: str) -> list[dict[str, str]]:
    wanted_level = (data_level or "both").lower()
    rows: list[dict[str, str]] = []
    for spec in specs:
        seller_id = spec.seller_id.strip()
        if not seller_id:
            continue
        if wanted_level in ("seller", "both"):
            rows.append(
                {
                    "seller_id": seller_id,
                    "data_level": "seller",
                    "data_type": "seller_sales",
                    "query_source_table": "item_seller_sales" if spec.use_item_sales else "seller_sales",
                }
            )
            rows.append(
                {
                    "seller_id": seller_id,
                    "data_level": "seller",
                    "data_type": "seller_traffic",
                    "query_source_table": "seller_traffic",
                }
            )
        if wanted_level in ("sku", "both"):
            rows.append(
                {
                    "seller_id": seller_id,
                    "data_level": "sku",
                    "data_type": "sku_sales",
                    "query_source_table": "item_sku_sales" if spec.use_item_sales else "sku_sales",
                }
            )
            rows.append(
                {
                    "seller_id": seller_id,
                    "data_level": "sku",
                    "data_type": "sku_traffic",
                    "query_source_table": "sku_traffic",
                }
            )
    return rows


def run_db_batch(
    credentials: DbCredentials,
    specs: list[SellerFileSpec],
    start_date: str,
    end_date: str,
    granularity: str,
    output_dir: Path,
    data_level: str = "both",
) -> dict[str, Any]:
    platform_parts: list[pd.DataFrame] = []
    mappings: list[dict[str, str]] = []
    errors: list[str] = []

    for spec in specs:
        try:
            platform_norm, file_mappings, file_errors = read_platform_file(spec, "day")
            platform_parts.append(platform_norm)
            mappings.extend(file_mappings)
            errors.extend(file_errors)
        except Exception as exc:
            errors.append(f"{spec.file_path.name}: {exc}")

    if not platform_parts:
        raise ValueError("Khong doc duoc file platform nao. " + " | ".join(errors))

    platform_norm = pd.concat(platform_parts, ignore_index=True)
    db_parts: list[pd.DataFrame] = []
    query_debug: list[dict[str, Any]] = []
    query_jobs = sorted({(spec.seller_id, spec.use_item_sales) for spec in specs if spec.seller_id.strip()})
    for seller_id, use_item_sales in query_jobs:
        try:
            db_frame, debug_rows = query_seller_sources_with_debug(
                credentials,
                seller_id,
                start_date,
                end_date,
                data_level=data_level,
                use_item_sales=use_item_sales,
            )
            db_parts.append(db_frame)
            query_debug.extend(debug_rows)
        except Exception as exc:
            errors.append(f"{seller_id}: {exc}")

    db_by_source = pd.concat(db_parts, ignore_index=True) if db_parts else pd.DataFrame()
    result = compare_platform_to_db_sources(
        platform_norm,
        db_by_source,
        "day",
        output_dir,
        data_level=data_level,
        expected_query_tables=_expected_query_tables_for_specs(specs, data_level),
    )

    report_path = Path(result["report_path"])
    with pd.ExcelWriter(report_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        pd.DataFrame(mappings).to_excel(writer, sheet_name="Column_Mapping", index=False)
        pd.DataFrame({"error": errors}).to_excel(writer, sheet_name="Errors", index=False)
        pd.DataFrame(query_debug).to_excel(writer, sheet_name="DB_Query_Debug", index=False)

    result["errors"] = errors
    result["query_debug"] = query_debug
    return result
