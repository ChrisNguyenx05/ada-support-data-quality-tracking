from __future__ import annotations

import cgi
import json
import mimetypes
import os
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from dq_checker.batch import run_db_batch
from dq_checker.core import CompareOptions, SellerFileSpec, compare_files, save_upload, temp_upload_dir
from dq_checker.db import DbCredentials
from dq_checker.direct_query import run_direct_metric_query, run_monthly_check


ROOT = Path(__file__).resolve().parent


def _writable_output_dir() -> Path:
    candidates = [
        Path(os.getenv("DQ_OUTPUT_DIR", "")).expanduser() if os.getenv("DQ_OUTPUT_DIR") else None,
        Path(tempfile.gettempdir()) / "dq_outputs",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
            resolved.mkdir(parents=True, exist_ok=True)
            probe = tempfile.NamedTemporaryFile(dir=resolved, delete=True)
            probe.close()
            return resolved
        except OSError:
            continue
    raise RuntimeError("No writable output directory is available for generated reports.")


OUTPUTS = _writable_output_dir()


HTML = r"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Data Quality Batch Checker</title>
  <style>
    :root { --ink:#17202a; --muted:#64748b; --line:#d8dee9; --bg:#f6f8fb; --panel:#ffffff; --blue:#165dff; --green:#0f8a5f; --red:#c2410c; --yellow:#a16207; }
    * { box-sizing:border-box; }
    body { margin:0; font-family: Inter, Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--ink); }
    header { padding:18px 24px; border-bottom:1px solid var(--line); background:#fff; display:flex; align-items:center; justify-content:space-between; gap:16px; }
    h1 { margin:0; font-size:20px; letter-spacing:0; }
    main { padding:22px; max-width:1360px; margin:0 auto; display:grid; grid-template-columns:380px 1fr; gap:18px; }
    section, aside { background:var(--panel); border:1px solid var(--line); border-radius:8px; }
    aside { padding:16px; height:max-content; }
    section { min-height:640px; overflow:hidden; }
    label { display:block; font-size:12px; font-weight:700; color:#334155; margin:14px 0 6px; }
    input, select, button { width:100%; border:1px solid var(--line); border-radius:6px; padding:9px 10px; font:inherit; background:#fff; }
    input[type=file] { padding:8px; }
    button { margin-top:16px; background:var(--blue); color:#fff; border-color:var(--blue); cursor:pointer; font-weight:700; }
    button:disabled { opacity:.6; cursor:progress; }
    .hint { color:var(--muted); font-size:12px; line-height:1.45; margin-top:10px; }
    .topbar { padding:14px 16px; border-bottom:1px solid var(--line); display:flex; align-items:center; justify-content:space-between; gap:12px; }
    .cards { display:grid; grid-template-columns:repeat(4, minmax(120px, 1fr)); gap:10px; padding:16px; }
    .metric { border:1px solid var(--line); border-radius:8px; padding:12px; background:#fff; }
    .metric b { display:block; font-size:22px; margin-bottom:4px; }
    .metric span { color:var(--muted); font-size:12px; }
    .content { padding:0 16px 16px; }
    table { width:100%; border-collapse:collapse; font-size:12px; background:#fff; }
    th, td { border-bottom:1px solid #e6eaf0; padding:8px 9px; text-align:left; white-space:nowrap; }
    th { color:#334155; background:#f8fafc; position:sticky; top:0; }
    .table-wrap { max-height:430px; overflow:auto; border:1px solid var(--line); border-radius:8px; }
    .status { font-weight:700; }
    .match { color:var(--green); }
    .mismatch, .missing_in_db, .suspicious_extra_source { color:var(--red); }
    .missing_in_platform { color:var(--yellow); }
    .download { width:auto; margin:0; padding:8px 11px; text-decoration:none; color:#fff; background:var(--green); border-radius:6px; font-weight:700; font-size:13px; display:none; }
    .error { color:var(--red); padding:12px 16px; display:none; }
    .inline { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    .quick { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    .quick button { margin-top:0; background:#fff; color:var(--blue); }
    .mapping { margin-top:14px; max-height:270px; overflow:auto; border:1px solid var(--line); border-radius:8px; }
    .mapping input, .mapping select { padding:6px; font-size:12px; min-width:120px; }
    .mapping input[type=checkbox] { min-width:auto; width:auto; }
    @media (max-width:900px) { main { grid-template-columns:1fr; padding:12px; } .cards { grid-template-columns:1fr 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Data Quality Batch Checker</h1>
    <div class="hint">Multi-file platform check + PostgreSQL source analysis</div>
  </header>
  <main>
    <aside>
      <form id="batchForm">
        <label>Client</label>
        <select name="client">
          <option value="darlie">darlie</option>
          <option value="loreal_group_ph">loreal_group_ph</option>
          <option value="nestle_purina">nestle_purina</option>
        </select>
        <div class="inline">
          <div><label>DB username</label><input name="username" autocomplete="username" required></div>
          <div><label>DB password</label><input name="password" type="password" autocomplete="current-password" required></div>
        </div>
        <label>Date range</label>
        <div class="inline">
          <input name="start_date" id="startDate" type="date" required>
          <input name="end_date" id="endDate" type="date" required>
        </div>
        <label>Quick range</label>
        <div class="quick">
          <button type="button" id="oneWeek">1 Week</button>
          <button type="button" id="oneMonth">1 Month</button>
        </div>
        <label>Compare detail</label>
        <select name="granularity" id="granularity">
          <option value="day">Daily rows inside selected range</option>
        </select>
        <label>Check level</label>
        <select name="data_level">
          <option value="sku">SKU only</option>
          <option value="seller">Seller only</option>
          <option value="both">Seller + SKU</option>
        </select>
        <label>Platform exports (.xlsx/.csv, multi-select)</label>
        <input type="file" id="platformFiles" name="platform_files" multiple required>
        <div class="mapping">
          <table>
            <thead><tr><th>File</th><th>Seller ID</th><th>Platform</th><th>Item?</th><th>Sheet</th></tr></thead>
            <tbody id="fileMap"><tr><td colspan="5">Choose files first.</td></tr></tbody>
          </table>
        </div>
        <button id="run" type="submit">Run batch check</button>
      </form>
      <p class="hint">Password is only used for the current run and is not saved. Old .xls files should be saved as .xlsx or CSV first.</p>
    </aside>
    <section>
      <div class="topbar">
        <strong>Result</strong>
        <a id="download" class="download" href="#">Download report</a>
      </div>
      <div id="error" class="error"></div>
      <div class="cards" id="cards"></div>
      <div class="content">
        <div class="table-wrap">
          <table>
            <thead><tr><th>Status</th><th>Seller</th><th>Period</th><th>Level</th><th>Type</th><th>Metric</th><th>Platform</th><th>DB all sources</th><th>Diff</th><th>Matching source</th></tr></thead>
            <tbody id="rows"><tr><td colspan="10">Upload files to start.</td></tr></tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
  <script>
    const form = document.querySelector('#batchForm');
    const btn = document.querySelector('#run');
    const rows = document.querySelector('#rows');
    const cards = document.querySelector('#cards');
    const error = document.querySelector('#error');
    const download = document.querySelector('#download');
    const fileInput = document.querySelector('#platformFiles');
    const fileMap = document.querySelector('#fileMap');
    const startDate = document.querySelector('#startDate');
    const endDate = document.querySelector('#endDate');
    const granularity = document.querySelector('#granularity');
    const fmt = n => Number(n || 0).toLocaleString(undefined, {maximumFractionDigits: 2});
    const iso = d => d.toISOString().slice(0, 10);
    function setRange(days) {
      const end = new Date();
      const start = new Date();
      start.setDate(end.getDate() - days + 1);
      startDate.value = iso(start);
      endDate.value = iso(end);
      granularity.value = 'day';
    }
    document.querySelector('#oneWeek').addEventListener('click', () => setRange(7));
    document.querySelector('#oneMonth').addEventListener('click', () => setRange(30));
    setRange(7);
    fileInput.addEventListener('change', () => {
      const files = [...fileInput.files];
      fileMap.innerHTML = files.map((file, i) => {
        const guessed = (file.name.match(/[A-Z]{2}\.(SHP|LAZ|TTK)\.[A-Za-z0-9_-]+/i) || [''])[0].toUpperCase();
        const platform = (guessed.match(/\.(SHP|LAZ|TTK)\./) || [,'AUTO'])[1];
        return `<tr>
          <td>${file.name}</td>
          <td><input name="seller_${i}" value="${guessed}" placeholder="TH.LAZ.100192131567" required></td>
          <td><select name="marketplace_${i}"><option ${platform==='AUTO'?'selected':''}>AUTO</option><option ${platform==='SHP'?'selected':''}>SHP</option><option ${platform==='LAZ'?'selected':''}>LAZ</option><option ${platform==='TTK'?'selected':''}>TTK</option></select></td>
          <td><input name="use_item_sales_${i}" type="checkbox"></td>
          <td><input name="sheet_${i}" placeholder="optional"></td>
        </tr>`;
      }).join('') || '<tr><td colspan="5">Choose files first.</td></tr>';
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      btn.disabled = true;
      error.style.display = 'none';
      download.style.display = 'none';
      cards.innerHTML = '';
      rows.innerHTML = '<tr><td colspan="10">Checking DB and sources...</td></tr>';
      try {
        const fd = new FormData(form);
        const files = [...fileInput.files];
        const mapping = files.map((file, i) => ({
          fileName: file.name,
          sellerId: fd.get(`seller_${i}`),
          marketplace: fd.get(`marketplace_${i}`),
          sheet: fd.get(`sheet_${i}`),
          useItemSales: fd.get(`use_item_sales_${i}`) === 'on'
        }));
        fd.append('mapping_json', JSON.stringify(mapping));
        const res = await fetch('/api/batch-db', { method:'POST', body:fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Compare failed');
        const byStatus = Object.fromEntries((data.summary || []).map(x => [x.status, x.count]));
        const items = ['match','mismatch','missing_in_db','suspicious_extra_source'];
        cards.innerHTML = items.map(k => `<div class="metric"><b class="${k}">${byStatus[k] || 0}</b><span>${k}</span></div>`).join('');
        rows.innerHTML = (data.comparison || []).map(r => `
          <tr>
            <td class="status ${r.status}">${r.status}</td><td>${r.seller_id || ''}</td><td>${r.period}</td><td>${r.data_level || ''}</td><td>${r.data_type || ''}</td><td>${r.metric}</td>
            <td>${fmt(r.platform_value)}</td><td>${fmt(r.db_all_sources)}</td><td>${fmt(r.diff_db_minus_platform)}</td><td>${r.matching_source_alone || ''}</td>
          </tr>`).join('') || '<tr><td colspan="10">No comparable rows.</td></tr>';
        download.href = '/download?path=' + encodeURIComponent(data.report_path);
        download.style.display = 'inline-block';
      } catch (e) {
        error.textContent = e.message;
        error.style.display = 'block';
        rows.innerHTML = '<tr><td colspan="10">No result.</td></tr>';
      } finally {
        btn.disabled = false;
      }
    });
  </script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str = "text/plain") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/runtime":
            body = {
                "status": "ok",
                "entrypoint": "app.py",
                "output_dir": str(OUTPUTS),
                "dq_output_dir_env": os.getenv("DQ_OUTPUT_DIR", ""),
            }
            self._send(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/download":
            query = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
            target = Path(unquote(query.get("path", ""))).resolve()
            if not str(target).startswith(str(OUTPUTS.resolve())) or not target.exists():
                self._send(404, b"Report not found")
                return
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            self.wfile.write(target.read_bytes())
            return
        self._send(404, b"Not found")

    def do_POST(self) -> None:
        if self.path not in ("/api/compare", "/api/batch-db", "/api/query-data", "/api/monthly-check"):
            self._send(404, b"Not found")
            return
        try:
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
            if self.path == "/api/monthly-check":
                result = run_monthly_check(
                    credentials=DbCredentials(
                        client=form.getfirst("client") or "darlie",
                        username=form.getfirst("username") or "",
                        password=form.getfirst("password") or "",
                    ),
                    seller_ids_text=form.getfirst("seller_ids") or "",
                    target_month=form.getfirst("target_month") or "",
                    sources_text=form.getfirst("sources") or "all",
                    company=form.getfirst("company") or "",
                    output_dir=OUTPUTS,
                )
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            if self.path == "/api/query-data":
                result = run_direct_metric_query(
                    credentials=DbCredentials(
                        client=form.getfirst("client") or "darlie",
                        username=form.getfirst("username") or "",
                        password=form.getfirst("password") or "",
                    ),
                    seller_id=form.getfirst("seller_id") or "",
                    start_date=form.getfirst("start_date") or "",
                    end_date=form.getfirst("end_date") or "",
                    metric=form.getfirst("metric") or "all",
                    output_dir=OUTPUTS,
                    data_level=form.getfirst("data_level") or "both",
                    use_item_sales=(form.getfirst("use_item_sales") or "").lower() in ("1", "true", "on", "yes"),
                    query_flow=form.getfirst("query_flow") or "all",
                )
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            if self.path == "/api/batch-db":
                upload_dir = temp_upload_dir()
                files_field = form["platform_files"]
                files = files_field if isinstance(files_field, list) else [files_field]
                saved_by_name = {field.filename: save_upload(field, upload_dir) for field in files if field.filename}
                mapping = json.loads(form.getfirst("mapping_json") or "[]")
                specs = []
                for row in mapping:
                    file_name = row.get("fileName", "")
                    seller_id = (row.get("sellerId") or "").strip()
                    if not file_name or not seller_id:
                        raise ValueError("Moi file can co seller_id.")
                    specs.append(
                        SellerFileSpec(
                            file_path=saved_by_name[file_name],
                            seller_id=seller_id,
                            marketplace=(row.get("marketplace") or "AUTO").upper(),
                            platform_sheet=(row.get("sheet") or "").strip() or None,
                            use_item_sales=bool(row.get("useItemSales")),
                        )
                    )
                result = run_db_batch(
                    credentials=DbCredentials(
                        client=form.getfirst("client") or "darlie",
                        username=form.getfirst("username") or "",
                        password=form.getfirst("password") or "",
                    ),
                    specs=specs,
                    start_date=form.getfirst("start_date") or "",
                    end_date=form.getfirst("end_date") or "",
                    granularity=form.getfirst("granularity") or "day",
                    output_dir=OUTPUTS,
                    data_level=form.getfirst("data_level") or "sku",
                )
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return

            upload_dir = temp_upload_dir()
            platform_file = save_upload(form["platform_file"], upload_dir)
            db_file = save_upload(form["db_file"], upload_dir)
            options = CompareOptions(
                marketplace=(form.getfirst("marketplace") or "AUTO").upper(),
                seller_id=form.getfirst("seller_id") or "",
                granularity=form.getfirst("granularity") or "day",
                platform_sheet=(form.getfirst("platform_sheet") or "").strip() or None,
            )
            result = compare_files(platform_file, db_file, OUTPUTS, options)
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        except Exception as exc:
            self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    print("Data Quality Checker is running at http://127.0.0.1:8765")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
