"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useState } from 'react';
import { Link } from "@/lib/navigation";
import { ArrowLeft, ArrowRight, Search, Truck } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { formatDate } from '@/lib/dates';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
export default function Challans() {
  const [data, setData] = useState({
    rows: [],
    firms: [],
    total: 0,
    pages: 1
  });
  const [firm, setFirm] = useState(''),
    [query, setQuery] = useState(''),
    [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = setTimeout(() => api.get('/challans', {
      params: {
        firm: firm || undefined,
        q: query,
        page
      },
      signal: controller.signal
    }).then(r => setData(r.data)).catch(e => {
      if (e.code !== 'ERR_CANCELED') setError(errorText(e));
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    }), 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [firm, query, page]);
  return <div className={workspaceClasses("page")}><PageTitle eyebrow="WORKSPACE / CHALLANS" title="Dispatched challans" />
    <div className={workspaceClasses("summary-grid challan-summary")}><div className={workspaceClasses("summary-stat")}><span>Firm</span><strong data-testid="challans-firm-label">{firm || 'All firms'}</strong></div><div className={workspaceClasses("summary-stat")}><span>Dispatch records</span><strong data-testid="challans-count">{number(data.total)}</strong></div></div>
    <div className={workspaceClasses("toolbar filters")}><div className={workspaceClasses("search")}><Search size={17} /><input value={query} maxLength={120} onChange={e => {
          setQuery(e.target.value);
          setPage(1);
        }} placeholder="Challan, party, or order" data-testid="challans-search-input" /></div>
      <select value={firm} onChange={e => {
        setFirm(e.target.value);
        setPage(1);
      }} data-testid="challans-firm-select"><option value="">All firms</option>{data.firms.map(f => <option key={f} value={f}>{f}</option>)}</select>
    </div>
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="challans-error">{error}</div>}
    {loading ? <div className={workspaceClasses("loading")} data-testid="challans-loading">Fetching challans…</div> : !error && <>
      {!data.rows.length ? <div className={workspaceClasses("empty")} data-testid="challans-empty"><Truck size={26} /><h3>{firm || query ? 'No matching challans' : 'No challans yet'}</h3></div> : <div className={workspaceClasses("table-wrap")}><table className={workspaceClasses("responsive-table")}><thead><tr>{['Challan', 'Firm', 'Sent', 'Party', 'Order', 'Contents', ''].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{data.rows.map(r => {
              const id = `${r.order_id}-${r.parcel_index}`;
              return <tr key={id} data-testid={`challan-row-${id}`}>
          <td data-label="Challan" data-testid={`challan-number-${id}`}><strong>{r.challan_number}</strong></td>
          <td data-label="Firm" data-testid={`challan-firm-${id}`}>{r.firm}</td>
          <td data-label="Sent" data-testid={`challan-sent-${id}`}>{formatDate(r.sent_at)}</td>
          <td data-label="Party" className={workspaceClasses("party-cell")} data-testid={`challan-party-${id}`}>{r.party_name}</td>
          <td data-label="Order" data-testid={`challan-order-${id}`}>{r.order_number}<small data-testid={`challan-order-date-${id}`}> · {formatDate(r.order_date)}</small></td>
          <td data-label="Contents" className={workspaceClasses("challan-contents")} data-testid={`challan-contents-${id}`}>{r.compositions.map((c, i) => <div key={i}>{c.catalogue_name} <b>{c.volume_name}</b></div>)}</td>
          <td data-label=""><Link to={`/orders/${r.order_id}`} className={workspaceClasses("row-open")} data-testid={`challan-open-${id}`}>Open<ArrowRight size={14} /></Link></td>
        </tr>;
            })}</tbody></table></div>}
      <div className={workspaceClasses("pagination")}><Button variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)} data-testid="challans-previous-page"><ArrowLeft size={15} />Previous</Button><span data-testid="challans-page-indicator">Page {page} of {data.pages}</span><Button variant="outline" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)} data-testid="challans-next-page">Next<ArrowRight size={15} /></Button></div>
    </>}
  </div>;
}
