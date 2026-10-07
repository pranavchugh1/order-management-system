"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useState } from 'react';
import { useNavigate } from "@/lib/navigation";
import { ArrowLeft, ArrowRight, ListPlus, Plus, Search } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { PageTitle, Button } from '@/components/WorkspacePrimitives';
import { ExportButton } from '@/components/ExportButton';
import { formatDate } from '@/lib/dates';
export default function Orders({
  status = 'all'
}) {
  const [data, setData] = useState({
    items: [],
    total: 0,
    pages: 1
  });
  const [query, setQuery] = useState(''),
    [page, setPage] = useState(1),
    [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  const navigate = useNavigate();
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = setTimeout(() => api.get('/orders', {
      params: {
        status,
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
  }, [status, query, page]);
  const title = status === 'all' ? 'All orders' : status === 'pending' ? 'Pending orders' : 'Completed orders';
  return <div className={workspaceClasses("page")}><PageTitle eyebrow="WORKSPACE / ORDERS" title={title} description={status === 'completed' ? 'Every parcel dispatched.' : 'The day’s orders, all in view.'} action={<div className={workspaceClasses("page-actions")}><ExportButton /><Button variant="outline" onClick={() => navigate('/bulk')} data-testid="bulk-order-button"><ListPlus size={16} />Bulk entry</Button><Button onClick={() => navigate('/orders/new')} data-testid="new-order-button"><Plus size={16} />New order</Button></div>} />
    <div className={workspaceClasses("toolbar")}><div className={workspaceClasses("search")}><Search size={17} /><input value={query} onChange={e => {
          setQuery(e.target.value);
          setPage(1);
        }} placeholder="Order number or party name" maxLength={120} data-testid="orders-search-input" /></div><span className={workspaceClasses("result-count")} data-testid="orders-result-count">{number(data.total)} orders</span></div>
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="orders-error">{error}</div>}
    {loading ? <div className={workspaceClasses("loading")} data-testid="orders-loading">Loading orders…</div> : !error && <>
      {!data.items.length ? <div className={workspaceClasses("empty")} data-testid="orders-empty"><h3>{query ? 'No matching orders' : `No ${status === 'all' ? '' : status + ' '}orders`}</h3></div> : <div className={workspaceClasses("table-wrap")}><table className={workspaceClasses("responsive-table clickable-rows")}><thead><tr>{['Order', 'Date', 'Party', 'Parcels', 'Pieces', 'Status', 'Remarks'].map(t => <th key={t}>{t}</th>)}</tr></thead><tbody>{data.items.map(o => <tr key={o.id} tabIndex={0} role="link" aria-label={`Open order ${o.order_number} for ${o.party_name}`} onClick={() => navigate(`/orders/${o.id}`)} onKeyDown={e => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate(`/orders/${o.id}`);
              }
            }} data-testid={`order-row-${o.order_number}`}>
        <td data-label="Order"><span className={workspaceClasses("order-number")} data-testid={`order-link-${o.id}`}>{o.order_number}</span></td><td data-label="Date" data-testid={`order-date-${o.id}`}>{formatDate(o.date)}</td><td className={workspaceClasses("party-cell")} data-label="Party" data-testid={`order-party-${o.id}`}>{o.party_name}</td><td data-label="Parcels" data-testid={`order-parcels-${o.id}`}>{o.parcel_count}</td><td data-label="Pieces" data-testid={`order-pieces-${o.id}`}>{number(o.total_pieces)}</td>
        <td data-label="Status"><span className={workspaceClasses(`status ${o.state === 'completed' ? 'sent' : ''}`)} data-testid={`order-status-${o.id}`}>{o.state === 'completed' ? 'Completed' : o.pending_parcels < o.parcel_count ? 'Partially Pending' : 'Pending'}</span></td><td data-label="Remarks" className={workspaceClasses("remarks")}>{o.remarks || '—'}</td>
      </tr>)}</tbody></table></div>}
      <div className={workspaceClasses("pagination")}><Button variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)} data-testid="orders-previous-page"><ArrowLeft size={15} />Previous</Button><span data-testid="orders-page-indicator">Page {page} of {data.pages}</span><Button variant="outline" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)} data-testid="orders-next-page">Next<ArrowRight size={15} /></Button></div>
    </>}
  </div>;
}
