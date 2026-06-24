from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from dq_checker.core import SellerFileSpec, compare_platform_to_db_sources, read_platform_file
from dq_checker.db import DbCredentials, query_seller_sources


def run_db_batch(
    credentials: DbCredentials,
    specs: list[SellerFileSpec],
    start_date: str,
    end_date: str,
    granularity: str,
    output_dir: Path,
) -> dict[str, Any]:
    platform_parts: list[pd.DataFrame] = []
    mappings: list[dict[str, str]] = []
    errors: list[str] = []

    for spec in specs:
        try:
            platform_norm, file_mappings, file_errors = read_platform_file(spec, granularity)
            platform_parts.append(platform_norm)
            mappings.extend(file_mappings)
            errors.extend(file_errors)
        except Exception as exc:
            errors.append(f"{spec.file_path.name}: {exc}")

    if not platform_parts:
        raise ValueError("Khong doc duoc file platform nao. " + " | ".join(errors))

    platform_norm = pd.concat(platform_parts, ignore_index=True)
    db_parts: list[pd.DataFrame] = []
    for seller_id in sorted({spec.seller_id for spec in specs if spec.seller_id.strip()}):
        try:
            db_parts.append(query_seller_sources(credentials, seller_id, start_date, end_date))
        except Exception as exc:
            errors.append(f"{seller_id}: {exc}")

    db_by_source = pd.concat(db_parts, ignore_index=True) if db_parts else pd.DataFrame()
    result = compare_platform_to_db_sources(platform_norm, db_by_source, granularity, output_dir)

    report_path = Path(result["report_path"])
    with pd.ExcelWriter(report_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        pd.DataFrame(mappings).to_excel(writer, sheet_name="Column_Mapping", index=False)
        pd.DataFrame({"error": errors}).to_excel(writer, sheet_name="Errors", index=False)

    result["errors"] = errors
    return result
