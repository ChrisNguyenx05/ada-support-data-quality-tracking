import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const DEFAULT_API_BASE = 'https://ada-support-data-quality-tracking.onrender.com';
const API_BASE = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE).replace(/\/$/, '');

function iso(date) {
  return date.toISOString().slice(0, 10);
}

function setQuickRange(days) {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - days + 1);
  return { startDate: iso(start), endDate: iso(end), granularity: 'day' };
}

function guessSeller(fileName) {
  return (fileName.match(/[A-Z]{2}\.(SHP|LAZ|TTK)\.[A-Za-z0-9_-]+/i) || [''])[0].toUpperCase();
}

function guessPlatform(sellerId) {
  return (sellerId.match(/\.(SHP|LAZ|TTK)\./) || [null, 'AUTO'])[1];
}

function number(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function optionalNumber(value, available = true) {
  if (!available || value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return number(value);
}

const SELLER_COLORS = ['#E8F3FF', '#EAF8EE', '#FFF4DE', '#F3EAFE', '#FFEAEA', '#E9F7F8', '#F8F0E7', '#EEF2FF'];

function sellerColor(sellerId) {
  const text = String(sellerId || '');
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) hash = (hash + text.charCodeAt(i)) % 997;
  return SELLER_COLORS[hash % SELLER_COLORS.length];
}

function App() {
  const [mode, setMode] = useState('query');
  const [clients, setClients] = useState(['darlie', 'loreal_group_ph', 'nestle_purina']);
  const [client, setClient] = useState('darlie');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [range, setRange] = useState(setQuickRange(7));
  const [dataLevel, setDataLevel] = useState('sku');
  const [querySellerId, setQuerySellerId] = useState('');
  const [queryMetric, setQueryMetric] = useState('all');
  const [queryFlow, setQueryFlow] = useState('all');
  const [queryUseItemSales, setQueryUseItemSales] = useState(false);
  const [monthlySellerIds, setMonthlySellerIds] = useState('');
  const [monthlyMonth, setMonthlyMonth] = useState(() => iso(new Date()).slice(0, 7));
  const [monthlySources, setMonthlySources] = useState(['export_sku_sale']);
  const [monthlyCompany, setMonthlyCompany] = useState('nestle_purina');
  const [files, setFiles] = useState([]);
  const [mapping, setMapping] = useState([]);
  const [result, setResult] = useState(null);
  const [queryResult, setQueryResult] = useState(null);
  const [monthlyResult, setMonthlyResult] = useState(null);
  const [selectedMetric, setSelectedMetric] = useState('all');
  const [selectedStatus, setSelectedStatus] = useState('all');
  const [selectedTable, setSelectedTable] = useState('all');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/clients`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => data?.clients && setClients(data.clients))
      .catch(() => {});
  }, []);

  const summary = useMemo(() => {
    return Object.fromEntries((result?.summary || []).map((row) => [row.status, row.count]));
  }, [result]);

  const queryRows = useMemo(() => queryResult?.by_day || [], [queryResult]);
  const queryTotals = useMemo(() => queryResult?.summary || [], [queryResult]);
  const monthlyRows = useMemo(() => monthlyResult?.rows || [], [monthlyResult]);
  const monthlySummary = useMemo(() => monthlyResult?.summary || [], [monthlyResult]);

  const metricOptions = useMemo(() => {
    const metrics = new Set((result?.comparison || []).map((row) => row.metric).filter(Boolean));
    return ['all', ...Array.from(metrics).sort()];
  }, [result]);

  const statusOptions = useMemo(() => {
    const statuses = new Set((result?.comparison || []).map((row) => row.status).filter(Boolean));
    return ['all', ...Array.from(statuses).sort()];
  }, [result]);

  const tableOptions = useMemo(() => {
    const tables = new Set((result?.comparison || []).map((row) => row.query_source_table || row.data_type).filter(Boolean));
    return ['all', ...Array.from(tables).sort()];
  }, [result]);

  const filteredComparison = useMemo(() => {
    const rows = result?.comparison || [];
    return rows.filter((row) => {
      const rowTable = row.query_source_table || row.data_type;
      return (
        (selectedMetric === 'all' || row.metric === selectedMetric)
        && (selectedStatus === 'all' || row.status === selectedStatus)
        && (selectedTable === 'all' || rowTable === selectedTable)
      );
    });
  }, [result, selectedMetric, selectedStatus, selectedTable]);

  const queryDebug = useMemo(() => result?.query_debug || [], [result]);
  const resultErrors = useMemo(() => (result?.errors || []).filter(Boolean), [result]);
  const missingOrderSummary = useMemo(() => result?.missing_order_summary || [], [result]);

  function updateMonthlySource(source, checked) {
    setMonthlySources((items) => {
      if (checked) return [...new Set([...items, source])];
      return items.filter((item) => item !== source);
    });
  }

  function onFiles(nextFiles) {
    const list = [...nextFiles];
    setFiles(list);
    setMapping(list.map((file) => {
      const sellerId = guessSeller(file.name);
      return { fileName: file.name, sellerId, marketplace: guessPlatform(sellerId), sheet: '', useItemSales: false };
    }));
  }

  function updateMap(index, key, value) {
    setMapping((rows) => rows.map((row, i) => i === index ? { ...row, [key]: value } : row));
  }

  async function submit(event) {
    event.preventDefault();
    setError('');
    setResult(null);
    setQueryResult(null);
    setMonthlyResult(null);
    setSelectedMetric('all');
    setSelectedStatus('all');
    setSelectedTable('all');
    setLoading(true);
    try {
      const form = new FormData();
      form.append('client', client);
      form.append('username', username);
      form.append('password', password);
      form.append('start_date', range.startDate);
      form.append('end_date', range.endDate);
      form.append('granularity', range.granularity);
      form.append('data_level', dataLevel);
      form.append('mapping_json', JSON.stringify(mapping));
      files.forEach((file) => form.append('platform_files', file));

      const res = await fetch(`${API_BASE}/api/batch-db`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Batch check failed');
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitDirectQuery(event) {
    event.preventDefault();
    setError('');
    setResult(null);
    setQueryResult(null);
    setMonthlyResult(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append('client', client);
      form.append('username', username);
      form.append('password', password);
      form.append('seller_id', querySellerId);
      form.append('metric', queryMetric);
      form.append('query_flow', queryFlow);
      form.append('start_date', range.startDate);
      form.append('end_date', range.endDate);
      form.append('data_level', dataLevel);
      form.append('use_item_sales', queryUseItemSales ? 'true' : 'false');

      const res = await fetch(`${API_BASE}/api/query-data`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Query failed');
      setQueryResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitMonthlyCheck(event) {
    event.preventDefault();
    setError('');
    setResult(null);
    setQueryResult(null);
    setMonthlyResult(null);
    setLoading(true);
    try {
      const form = new FormData();
      form.append('client', client);
      form.append('username', username);
      form.append('password', password);
      form.append('seller_ids', monthlySellerIds);
      form.append('target_month', `${monthlyMonth}-01`);
      form.append('sources', monthlySources.join(','));
      form.append('company', monthlyCompany);

      const res = await fetch(`${API_BASE}/api/monthly-check`, { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || 'Monthly check failed');
      setMonthlyResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const downloadHref = result?.download_url ? `${API_BASE}${result.download_url}` : '';
  const queryDownloadHref = queryResult?.download_url ? `${API_BASE}${queryResult.download_url}` : '';
  const monthlyDownloadHref = monthlyResult?.download_url ? `${API_BASE}${monthlyResult.download_url}` : '';

  return (
    <div>
      <header>
        <h1>Data Quality Batch Checker</h1>
        <span>API: {API_BASE}</span>
      </header>
      <main>
        <aside>
          <div className="mode-switch">
            <button type="button" className={mode === 'query' ? 'active' : ''} onClick={() => setMode('query')}>Query data</button>
            <button type="button" className={mode === 'monthly' ? 'active' : ''} onClick={() => setMode('monthly')}>Monthly Check</button>
            <button type="button" className={mode === 'batch' ? 'active' : ''} onClick={() => setMode('batch')}>Batch check</button>
          </div>

          <form onSubmit={mode === 'query' ? submitDirectQuery : (mode === 'monthly' ? submitMonthlyCheck : submit)}>
            <label>Client</label>
            <select value={client} onChange={(e) => setClient(e.target.value)}>
              {clients.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>

            <div className="inline">
              <div>
                <label>DB username</label>
                <input value={username} onChange={(e) => setUsername(e.target.value)} required />
              </div>
              <div>
                <label>DB password</label>
                <input value={password} onChange={(e) => setPassword(e.target.value)} type="password" required />
              </div>
            </div>

            {mode !== 'monthly' && (
              <>
                <label>Date range</label>
                <div className="inline">
                  <input type="date" value={range.startDate} onChange={(e) => setRange({ ...range, startDate: e.target.value })} required />
                  <input type="date" value={range.endDate} onChange={(e) => setRange({ ...range, endDate: e.target.value })} required />
                </div>

                <label>Quick range</label>
                <div className="quick">
                  <button type="button" onClick={() => setRange(setQuickRange(7))}>1 Week</button>
                  <button type="button" onClick={() => setRange(setQuickRange(30))}>1 Month</button>
                </div>

                <label>Compare detail</label>
                <select value="day" disabled>
                  <option value="day">Daily rows inside selected range</option>
                </select>

                <label>Check level</label>
                <select value={dataLevel} onChange={(e) => setDataLevel(e.target.value)}>
                  <option value="sku">SKU only</option>
                  <option value="seller">Seller only</option>
                  <option value="both">Seller + SKU</option>
                </select>
              </>
            )}

            {mode === 'query' && (
              <>
                <label>Seller ID</label>
                <input value={querySellerId} onChange={(e) => setQuerySellerId(e.target.value)} placeholder="TH.LAZ.100192131567" required />

                <label>Metric</label>
                <select value={queryMetric} onChange={(e) => setQueryMetric(e.target.value)}>
                  <option value="all">All</option>
                  <option value="sales">Sales: quantity + revenue</option>
                  <option value="traffic">Traffic: page_view</option>
                  <option value="quantity">quantity</option>
                  <option value="revenue">revenue</option>
                  <option value="page_view">page_view</option>
                </select>

                <label>Query flow</label>
                <select value={queryFlow} onChange={(e) => setQueryFlow(e.target.value)}>
                  <option value="all">All flows</option>
                  <option value="sku_traffic">SKU traffic</option>
                  <option value="sku_sales">SKU sales</option>
                  <option value="item_sku_sales">Item SKU sales</option>
                  <option value="seller_sales">Seller sales</option>
                  <option value="item_seller_sales">Item seller sales</option>
                  <option value="seller_traffic">Seller traffic</option>
                </select>

                <label className="checkbox-row">
                  <input checked={queryUseItemSales} onChange={(e) => setQueryUseItemSales(e.target.checked)} type="checkbox" />
                  Use ecommerce_item for sales
                </label>
              </>
            )}

            {mode === 'monthly' && (
              <>
                <label>Seller IDs</label>
                <textarea
                  value={monthlySellerIds}
                  onChange={(e) => setMonthlySellerIds(e.target.value)}
                  placeholder="ID.TTK.7494745179781958063&#10;ID.TTK.another_seller_id"
                  required
                />

                <label>Month</label>
                <input type="month" value={monthlyMonth} onChange={(e) => setMonthlyMonth(e.target.value)} required />

                <label>Company</label>
                <input value={monthlyCompany} onChange={(e) => setMonthlyCompany(e.target.value)} placeholder="nestle_purina" />

                <label>Source</label>
                <label className="checkbox-row">
                  <input checked={monthlySources.includes('item')} onChange={(e) => updateMonthlySource('item', e.target.checked)} type="checkbox" />
                  item
                </label>
                <label className="checkbox-row">
                  <input checked={monthlySources.includes('export_sku_sale')} onChange={(e) => updateMonthlySource('export_sku_sale', e.target.checked)} type="checkbox" />
                  export_sku_sale
                </label>
                <label className="checkbox-row">
                  <input checked={monthlySources.includes('export_sku_traffic')} onChange={(e) => updateMonthlySource('export_sku_traffic', e.target.checked)} type="checkbox" />
                  export_sku_traffic
                </label>
              </>
            )}

            {mode === 'batch' && (
              <>
                <label>Platform exports</label>
                <input type="file" multiple onChange={(e) => onFiles(e.target.files)} required={mode === 'batch'} />

                <div className="mapping">
                  <table>
                    <thead><tr><th>File</th><th>Seller ID</th><th>Platform</th><th>Item?</th><th>Sheet</th></tr></thead>
                    <tbody>
                      {mapping.length === 0 && <tr><td colSpan="5">Choose files first.</td></tr>}
                      {mapping.map((row, i) => (
                        <tr key={row.fileName}>
                          <td>{row.fileName}</td>
                          <td><input value={row.sellerId} onChange={(e) => updateMap(i, 'sellerId', e.target.value)} required={mode === 'batch'} /></td>
                          <td>
                            <select value={row.marketplace} onChange={(e) => updateMap(i, 'marketplace', e.target.value)}>
                              <option>AUTO</option><option>SHP</option><option>LAZ</option><option>TTK</option>
                            </select>
                          </td>
                          <td><input checked={row.useItemSales} onChange={(e) => updateMap(i, 'useItemSales', e.target.checked)} type="checkbox" /></td>
                          <td><input value={row.sheet} onChange={(e) => updateMap(i, 'sheet', e.target.value)} placeholder="optional" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            <button disabled={loading || (mode === 'batch' && files.length === 0) || (mode === 'monthly' && monthlySources.length === 0)}>
              {loading ? 'Running...' : (mode === 'query' ? 'Query data' : (mode === 'monthly' ? 'Run Monthly Check' : 'Run batch check'))}
            </button>
          </form>
          <p className="hint">Password is sent only to the backend for this run. Do not deploy the backend as a public app without access protection.</p>
        </aside>

        <section>
          <div className="topbar">
            <strong>Result</strong>
            {(result?.api_version || queryResult?.api_version) && <span>Backend: {result?.api_version || queryResult?.api_version}</span>}
            {monthlyResult?.api_version && <span>Backend: {monthlyResult.api_version}</span>}
            {monthlyDownloadHref && <a className="download" href={monthlyDownloadHref}>Download monthly</a>}
            {queryDownloadHref && <a className="download" href={queryDownloadHref}>Download query</a>}
            {downloadHref && <a className="download" href={downloadHref}>Download report</a>}
          </div>
          {error && <div className="error">{error}</div>}
          {monthlyResult && (
            <>
              <div className="cards">
                {monthlySummary.slice(0, 4).map((row, i) => (
                  <div className="metric" key={`${row.seller_id}-${row.source}-${i}`}>
                    <b>{number(row.sum_revenue || row.page_view || row.sum_quantity)}</b>
                    <span>{row.seller_id} / {row.source}</span>
                  </div>
                ))}
                {monthlySummary.length === 0 && <div className="metric"><b>0</b><span>No data</span></div>}
              </div>
              <div className="content">
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Company</th><th>Country</th><th>Marketplace</th><th>Seller</th><th>Month</th><th>Source</th><th>Quantity</th><th>Revenue</th><th>Page view</th><th>Product impression</th></tr></thead>
                    <tbody>
                      {monthlyRows.length === 0 && <tr><td colSpan="10">No data for selected params.</td></tr>}
                      {monthlyRows.map((row, i) => (
                        <tr key={`${row.seller_id}-${row.source}-${i}`} style={{ background: sellerColor(row.seller_id) }}>
                          <td>{row.company}</td>
                          <td>{row.country}</td>
                          <td>{row.marketplace}</td>
                          <td><span className="seller-badge">{row.seller_id}</span></td>
                          <td>{row.year_month}</td>
                          <td>{row.source}</td>
                          <td>{number(row.sum_quantity)}</td>
                          <td>{number(row.sum_revenue)}</td>
                          <td>{number(row.page_view)}</td>
                          <td>{number(row.product_impression)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
          {queryResult && (
            <>
              <div className="cards">
                {queryTotals.slice(0, 4).map((row, i) => (
                  <div className="metric" key={`${row.data_level}-${row.data_type}-${row.metric}-${i}`}>
                    <b>{number(row.value)}</b>
                    <span>{row.data_level} / {row.data_type} / {row.metric}</span>
                  </div>
                ))}
                {queryTotals.length === 0 && <div className="metric"><b>0</b><span>No data</span></div>}
              </div>
              <div className="content">
                <details className="debug-panel">
                  <summary>By source ({queryResult.by_source?.length || 0})</summary>
                  <div className="table-wrap debug-wrap">
                    <table>
                      <thead><tr><th>Level</th><th>Type</th><th>Query table</th><th>Source</th><th>Metric</th><th>Value</th></tr></thead>
                      <tbody>
                        {(queryResult.by_source || []).map((row, i) => (
                          <tr key={`${row.data_type}-${row.source}-${row.metric}-${i}`}>
                            <td>{row.data_level}</td>
                            <td>{row.data_type}</td>
                            <td>{row.query_source_table}</td>
                            <td>{row.source}</td>
                            <td>{row.metric}</td>
                            <td>{number(row.value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
                <details className="debug-panel">
                  <summary>DB query debug ({queryResult.query_debug?.length || 0})</summary>
                  <div className="table-wrap debug-wrap">
                    <table>
                      <thead><tr><th>Query table</th><th>Rows</th><th>Quantity</th><th>Revenue</th><th>Page view</th><th>Status</th><th>Error</th></tr></thead>
                      <tbody>
                        {(queryResult.query_debug || []).map((row, i) => (
                          <tr key={`${row.query_source_table}-${i}`}>
                            <td>{row.query_source_table}</td>
                            <td>{number(row.row_count)}</td>
                            <td>{number(row.quantity_sum)}</td>
                            <td>{number(row.revenue_sum)}</td>
                            <td>{number(row.page_view_sum)}</td>
                            <td className={row.status === 'error' ? 'status mismatch' : 'status match'}>{row.status}</td>
                            <td>{row.error}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Seller</th><th>Day</th><th>Level</th><th>Type</th><th>Metric</th><th>Value</th></tr></thead>
                    <tbody>
                      {queryRows.length === 0 && <tr><td colSpan="6">No data for selected inputs.</td></tr>}
                      {queryRows.map((row, i) => (
                        <tr key={`${row.seller_id}-${row.day}-${row.data_type}-${row.metric}-${i}`} style={{ background: sellerColor(row.seller_id) }}>
                          <td><span className="seller-badge">{row.seller_id}</span></td>
                          <td>{row.day}</td>
                          <td>{row.data_level}</td>
                          <td>{row.data_type}</td>
                          <td>{row.metric}</td>
                          <td>{number(row.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
          {resultErrors.length > 0 && (
            <div className="error">
              <strong>Backend errors:</strong> {resultErrors.join(' | ')}
            </div>
          )}
          {!queryResult && !monthlyResult && <div className="cards">
            {['match', 'mismatch', 'missing_in_db', 'suspicious_extra_source'].map((key) => (
              <div className="metric" key={key}><b className={key}>{summary[key] || 0}</b><span>{key}</span></div>
            ))}
          </div>}
          {!queryResult && !monthlyResult && <div className="content">
            {result && (
              <div className="result-tools">
                <div className="tool-group">
                  <span>Metric</span>
                  <div className="segmented">
                    {metricOptions.map((metric) => (
                      <button
                        key={metric}
                        type="button"
                        className={selectedMetric === metric ? 'active' : ''}
                        onClick={() => setSelectedMetric(metric)}
                      >
                        {metric === 'all' ? 'All' : metric}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="tool-group compact">
                  <span>Status</span>
                  <select value={selectedStatus} onChange={(e) => setSelectedStatus(e.target.value)}>
                    {statusOptions.map((status) => (
                      <option key={status} value={status}>{status === 'all' ? 'All' : status}</option>
                    ))}
                  </select>
                </div>
                <div className="tool-group compact">
                  <span>Query table</span>
                  <select value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)}>
                    {tableOptions.map((table) => (
                      <option key={table} value={table}>{table === 'all' ? 'All' : table}</option>
                    ))}
                  </select>
                </div>
                <span>{filteredComparison.length} rows</span>
              </div>
            )}
            {result && (
              <details className="debug-panel">
                <summary>DB query debug ({queryDebug.length})</summary>
                <div className="table-wrap debug-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Seller</th><th>Query table</th><th>Physical table</th><th>Rows</th><th>Quantity</th><th>Revenue</th><th>Page view</th><th>First day</th><th>Last day</th><th>Status</th><th>Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {queryDebug.length === 0 && (
                        <tr><td colSpan="11">Backend did not return query_debug. This usually means Render is still running an old deployment.</td></tr>
                      )}
                      {queryDebug.map((row, i) => (
                        <tr key={`${row.seller_id}-${row.query_source_table}-${i}`}>
                          <td>{row.seller_id}</td>
                          <td>{row.query_source_table}</td>
                          <td>{row.physical_table}</td>
                          <td>{number(row.row_count)}</td>
                          <td>{number(row.quantity_sum)}</td>
                          <td>{number(row.revenue_sum)}</td>
                          <td>{number(row.page_view_sum)}</td>
                          <td>{row.first_day}</td>
                          <td>{row.last_day}</td>
                          <td className={row.status === 'error' ? 'status mismatch' : 'status match'}>{row.status}</td>
                          <td>{row.error}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
            {missingOrderSummary.length > 0 && (
              <details className="debug-panel" open>
                <summary>Missing order summary ({missingOrderSummary.length})</summary>
                <div className="table-wrap debug-wrap">
                  <table>
                    <thead>
                      <tr><th>Seller</th><th>Period</th><th>Orders</th><th>Missing rows</th><th>Metrics</th><th>Query tables</th></tr>
                    </thead>
                    <tbody>
                      {missingOrderSummary.map((row, i) => (
                        <tr key={`${row.seller_id}-${row.period}-${i}`}>
                          <td>{row.seller_id}</td>
                          <td>{row.period}</td>
                          <td>{optionalNumber(row.platform_orders, row.platform_orders_available)}</td>
                          <td>{number(row.missing_rows)}</td>
                          <td>{row.missing_metrics}</td>
                          <td>{row.missing_query_tables}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
            <div className="table-wrap">
              <table>
                <thead><tr><th>Status</th><th>Seller</th><th>Period</th><th>Level</th><th>Type</th><th>Query table</th><th>Metric</th><th>Platform</th><th>Orders</th><th>DB all sources</th><th>Diff</th><th>Matching source</th></tr></thead>
                <tbody>
                  {!result && <tr><td colSpan="12">Upload files to start.</td></tr>}
                  {result && filteredComparison.length === 0 && <tr><td colSpan="12">No rows for selected filters.</td></tr>}
                  {filteredComparison.map((row, i) => (
                    <tr key={`${row.seller_id}-${row.period}-${row.data_type}-${row.metric}-${i}`} style={{ background: sellerColor(row.seller_id) }}>
                      <td className={`status ${row.status}`}>{row.status}</td>
                      <td><span className="seller-badge">{row.seller_id}</span></td>
                      <td>{row.period}</td>
                      <td>{row.data_level}</td>
                      <td>{row.data_type}</td>
                      <td>{row.query_source_table || row.data_type}</td>
                      <td>{row.metric}</td>
                      <td>{number(row.platform_value)}</td>
                      <td>{optionalNumber(row.platform_orders, row.platform_orders_available)}</td>
                      <td>{number(row.db_all_sources)}</td>
                      <td>{number(row.diff_db_minus_platform)}</td>
                      <td>{row.matching_source_alone}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>}
        </section>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
