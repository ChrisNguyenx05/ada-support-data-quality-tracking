# ada-support-data-quality-tracking

Local tool support Data Quality checks for daily, weekly, and monthly platform data.

## What This Tool Does

The tool compares:

- Platform export file from Shopee, Lazada, or TikTok (`.xlsx` or `.csv`)
- Database query result exported from DBeaver (`.xlsx` or `.csv`)

It normalizes common metrics, aggregates by day/week/month, then produces a report showing:

- `match`: platform and DB values are aligned
- `mismatch`: both sides have data but values differ
- `missing_in_db`: platform has data but DB export does not
- `missing_in_platform`: DB has data but platform export does not

The generated Excel report includes comparison rows, normalized data, duplicate key checks, and detected column mapping.

## Quick Start

1. Run `install_deps.bat` once to install the PostgreSQL driver.
2. Double-click `run_tool.bat`.
3. Open `http://127.0.0.1:8765` if the browser does not open automatically.
4. Choose client, enter DB username/password, date range, and granularity.
5. Upload multiple platform Excel files.
6. Fill the mapping table: file name, seller ID, platform, optional sheet.
7. Click `Run batch check`.
8. Download the generated report from the result screen.

The DB password is only used for the current run and is not saved.

## Suggested DB Export Columns

Seller-level sales:

- `seller`
- `day`
- `total_quantity`
- `revenue_local`

Seller-level traffic:

- `seller`
- `day`
- `total_page_view`

Monthly check:

- `seller_id`
- `year_month`
- `sum_quantity`
- `sum_revenue`
- `page_view`
- `product_impression`

The exact names can be adjusted in `config/metric_mapping.json`.

## Platform Notes

- Shopee: use sheet `Key Metrics` when available. For monthly checks, the tool uses date-range rows and skips daily rows to avoid double counting.
- TikTok: the tool auto-detects the `Daily data` table in the sample format.
- Lazada: old `.xls` files are not supported by the bundled runtime. Open the file in Excel and Save As `.xlsx`, or export as `.csv`.

## Mapping More Columns

If a platform file uses a different metric name, add it to:

`config/metric_mapping.json`

For example, if Lazada revenue is named `Net Revenue(Local)`, add it under:

```json
"LAZ": {
  "revenue": ["Revenue", "GMV", "Sales", "Net Revenue(Local)"]
}
```

Keep DB aliases under `db_aliases`.

## Direct DB Mode

The app can connect directly to these clients:

- `darlie`
- `loreal_group_ph`
- `nestle_purina`

Connection details live in `config/clients.json`. Add future clients there; do not remove existing clients unless they are retired.

For every uploaded seller file, the tool queries:

- `ecommerce_export_seller_sales`
- `ecommerce_export_seller_traffic`
- `ecommerce_export_sku_sales`
- `ecommerce_export_sku_traffic`

It filters by the seller ID you enter in the upload mapping table and the selected date range.

## Source Check Logic

For each seller, period, level, data type, and metric, the report checks:

- `all_sources_sum`: whether all DB sources summed together match platform
- `single_source_match`: whether one source alone matches platform
- `suspicious_extra_source`: one source alone matches, but all sources combined are higher or different
- `missing_in_db`: platform has value but DB has no matching value
- `mismatch`: DB has value but no source combination clearly matches platform

Tolerance is currently 0%.

## Batch Report Sheets

Generated batch reports include:

- `Summary`
- `Wrong_Data_Detail`
- `Source_Check_Detail`
- `Duplicate_Source`
- `Missing_In_DB`
- `Mismatch_Value`
- `Matched`
- `Raw_Platform_Normalized`
- `Raw_DB_By_Source`
- `Column_Mapping`
- `Errors`
