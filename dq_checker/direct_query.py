from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import pandas as pd

from dq_checker.db import DbCredentials, MONTHLY_SOURCE_OPTIONS, query_monthly_check, query_seller_sources_with_debug


METRIC_OPTIONS = {
    "all": ["quantity", "revenue", "page_view"],
    "quantity": ["quantity"],
    "revenue": ["revenue"],
    "page_view": ["page_view"],
    "sales": ["quantity", "revenue"],
    "traffic": ["page_view"],
}

QUERY_FLOW_OPTIONS = {
    "all": ["seller_sales", "seller_traffic", "sku_sales", "sku_traffic"],
    "sku_traffic": ["sku_traffic"],
    "sku_trafic": ["sku_traffic"],
    "sku_sales": ["sku_sales"],
    "sku_sale": ["sku_sales"],
    "item_sku_sales": ["item_sku_sales"],
    "item_sku_sale": ["item_sku_sales"],
    "seller_sales": ["seller_sales"],
    "seller_sale": ["seller_sales"],
    "item_seller_sales": ["item_seller_sales"],
    "item_seller_sale": ["item_seller_sales"],
    "seller_traffic": ["seller_traffic"],
    "seller_trafic": ["seller_traffic"],
}


def _metric_columns(metric: str) -> list[str]:
    key = (metric or "all").strip().lower()
    if key not in METRIC_OPTIONS:
        allowed = ", ".join(sorted(METRIC_OPTIONS))
        raise ValueError(f"Metric khong hop le: {metric}. Hay chon mot trong: {allowed}.")
    return METRIC_OPTIONS[key]


def _query_sources(query_flow: str) -> list[str]:
    key = (query_flow or "all").strip().lower()
    if key not in QUERY_FLOW_OPTIONS:
        allowed = ", ".join(sorted(QUERY_FLOW_OPTIONS))
        raise ValueError(f"Query flow khong hop le: {query_flow}. Hay chon mot trong: {allowed}.")
    return QUERY_FLOW_OPTIONS[key]


def _split_multi_value(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n,;]+", value or "") if item.strip()]


def _to_result_rows(df: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "seller_id",
                "day",
                "data_level",
                "data_type",
                "query_source_table",
                "source",
                "metric",
                "value",
            ]
        )

    work = df.copy()
    work["day"] = pd.to_datetime(work["day"], errors="coerce").dt.strftime("%Y-%m-%d")
    for metric in metrics:
        if metric not in work.columns:
            work[metric] = 0.0
        work[metric] = pd.to_numeric(work[metric], errors="coerce").fillna(0.0)

    id_cols = ["seller_id", "day", "data_level", "data_type", "query_source_table", "source"]
    long_df = work.melt(id_vars=id_cols, value_vars=metrics, var_name="metric", value_name="value")
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce").fillna(0.0)
    return long_df.sort_values(["day", "data_level", "data_type", "metric", "source"]).reset_index(drop=True)


def run_direct_metric_query(
    credentials: DbCredentials,
    seller_id: str,
    start_date: str,
    end_date: str,
    metric: str,
    output_dir: Path,
    data_level: str = "both",
    use_item_sales: bool = False,
    query_flow: str = "all",
) -> dict[str, Any]:
    seller_id = seller_id.strip()
    if not seller_id:
        raise ValueError("Can nhap seller_id.")

    metrics = _metric_columns(metric)
    query_sources = _query_sources(query_flow)
    db_frame, query_debug = query_seller_sources_with_debug(
        credentials=credentials,
        seller_id=seller_id,
        start_date=start_date,
        end_date=end_date,
        data_level=data_level,
        use_item_sales=use_item_sales,
        query_sources=query_sources,
    )
    rows = _to_result_rows(db_frame, metrics)

    by_day = (
        rows.groupby(["seller_id", "day", "data_level", "data_type", "metric"], dropna=False)["value"]
        .sum()
        .reset_index()
        if not rows.empty
        else pd.DataFrame(columns=["seller_id", "day", "data_level", "data_type", "metric", "value"])
    )
    by_source = (
        rows.groupby(["seller_id", "data_level", "data_type", "query_source_table", "source", "metric"], dropna=False)["value"]
        .sum()
        .reset_index()
        if not rows.empty
        else pd.DataFrame(columns=["seller_id", "data_level", "data_type", "query_source_table", "source", "metric", "value"])
    )
    totals = (
        rows.groupby(["seller_id", "data_level", "data_type", "metric"], dropna=False)["value"]
        .sum()
        .reset_index()
        if not rows.empty
        else pd.DataFrame(columns=["seller_id", "data_level", "data_type", "metric", "value"])
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_seller_id = re.sub(r"[^A-Za-z0-9_-]+", "_", seller_id).strip("_") or "seller"
    out_path = output_dir / f"direct_query_{safe_seller_id}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        totals.to_excel(writer, sheet_name="Totals", index=False)
        by_day.to_excel(writer, sheet_name="By_Day", index=False)
        by_source.to_excel(writer, sheet_name="By_Source", index=False)
        rows.to_excel(writer, sheet_name="Raw_By_Source", index=False)
        pd.DataFrame(query_debug).to_excel(writer, sheet_name="DB_Query_Debug", index=False)

    return {
        "seller_id": seller_id,
        "metric": metric,
        "metrics": metrics,
        "start_date": start_date,
        "end_date": end_date,
        "data_level": data_level,
        "use_item_sales": use_item_sales,
        "query_flow": query_flow,
        "query_sources": query_sources,
        "summary": totals.to_dict(orient="records"),
        "by_day": by_day.sort_values(["day", "data_level", "data_type", "metric"]).head(1000).to_dict(orient="records") if not by_day.empty else [],
        "by_source": by_source.sort_values(["data_level", "data_type", "metric", "source"]).head(1000).to_dict(orient="records") if not by_source.empty else [],
        "raw_rows": rows.head(1000).to_dict(orient="records") if not rows.empty else [],
        "row_count": int(len(rows)),
        "query_debug": query_debug,
        "report_path": str(out_path.resolve()),
    }


def run_monthly_check(
    credentials: DbCredentials,
    seller_ids_text: str,
    target_month: str,
    sources_text: str,
    company: str,
    output_dir: Path,
) -> dict[str, Any]:
    seller_ids = _split_multi_value(seller_ids_text)
    sources = _split_multi_value(sources_text)
    if not sources or "all" in {source.lower() for source in sources}:
        sources = MONTHLY_SOURCE_OPTIONS.copy()

    db_frame = query_monthly_check(
        credentials=credentials,
        seller_ids=seller_ids,
        target_month=target_month,
        sources=sources,
        company=company,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    month_label = pd.to_datetime(target_month, errors="coerce")
    safe_month = month_label.strftime("%Y%m") if pd.notna(month_label) else re.sub(r"[^A-Za-z0-9_-]+", "_", target_month)
    out_path = output_dir / f"monthly_check_{safe_month}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    totals = db_frame.copy()
    numeric_cols = ["sum_quantity", "sum_revenue", "page_view", "product_impression"]
    for col in numeric_cols:
        if col not in totals.columns:
            totals[col] = 0
        totals[col] = pd.to_numeric(totals[col], errors="coerce").fillna(0)
    summary = (
        totals.groupby(["company", "seller_id", "year_month", "source"], dropna=False)[numeric_cols]
        .sum()
        .reset_index()
        if not totals.empty
        else pd.DataFrame(columns=["company", "seller_id", "year_month", "source", *numeric_cols])
    )
    response_rows = db_frame.copy()
    response_summary = summary.copy()
    for frame in (response_rows, response_summary):
        for col in ("year_month", "query_date"):
            if col in frame.columns:
                frame[col] = pd.to_datetime(frame[col], errors="coerce").dt.strftime("%Y-%m-%d")

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        db_frame.to_excel(writer, sheet_name="Monthly_Check", index=False)
        pd.DataFrame(
            {
                "target_month": [target_month],
                "seller_ids": [", ".join(seller_ids)],
                "sources": [", ".join(sources)],
                "company": [(company or credentials.client)],
            }
        ).to_excel(writer, sheet_name="Params", index=False)

    return {
        "target_month": target_month,
        "seller_ids": seller_ids,
        "sources": sources,
        "company": company or credentials.client,
        "row_count": int(len(db_frame)),
        "summary": response_summary.to_dict(orient="records"),
        "rows": response_rows.head(1000).to_dict(orient="records"),
        "report_path": str(out_path.resolve()),
    }
