"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useState } from 'react';
import { useNavigate } from "@/lib/navigation";
import { ArrowRight, CheckCircle2, Search } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { formatDate } from '@/lib/dates';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { ExportButton } from '@/components/ExportButton';
import { Pagination } from '@/components/Pagination';
import { getMasterOptions } from '@/lib/master-options';
export default function Pending() {
  const [data, setData] = useState({
    rows: [],
    summary: {},
    suggestions: {
      ready_orders: [],
      ready_parcels: [],
      partial_parcels: []
    }
  });
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1), [catalogues, setCatalogues] = useState([]);
  const [cat, setCat] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  useEffect(() => { getMasterOptions('catalogues').then(setCatalogues).catch(e => setError(errorText(e))); }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true);
    const timer = setTimeout(() => api.get('/pending-requirements', { params: { q: query, catalogue_id: cat, page }, signal: controller.signal }).then(r => setData(r.data)).catch(e => { if (e.code !== 'ERR_CANCELED') setError(errorText(e)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); }), 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, cat, page]);
  const cats = catalogues.map(c => [c.id, c.name]);
  const rows = data.rows || [];
  const suggestions = data.suggestions || {
    ready_orders: [],
    ready_parcels: [],
    partial_parcels: []
  };
  return <div className={workspaceClasses("page")}><PageTitle eyebrow="WORKSPACE / REQUIREMENTS" title="Pending requirements" description="Catalogue and volume totals, with stock-ready dispatch suggestions." action={<ExportButton />} />
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="pending-error">{error}</div>}
    {loading ? <div className={workspaceClasses("loading")} data-testid="pending-loading">Calculating requirements...</div> : <>
      <div className={workspaceClasses("summary-grid")}>{[['orders', 'Pending orders'], ['parcels', 'Pending parcels'], ['sets', 'Pending sets'], ['pieces', 'Pending pieces']].map(([k, label]) => <div className={workspaceClasses("summary-stat")} key={k}><span>{label}</span><strong data-testid={`pending-summary-${k}`}>{number(data.summary[k])}</strong></div>)}</div>
      <section className={workspaceClasses("suggestions-panel")}>
        <div className={workspaceClasses("list-head")}><h2>Suggested dispatch from stock</h2><span>{number(suggestions.ready_orders.length + suggestions.ready_parcels.reduce((sum, group) => sum + group.parcels.length, 0))} ready</span></div>
        {!suggestions.ready_orders.length && !suggestions.ready_parcels.length && !suggestions.partial_parcels.length ? <div className={workspaceClasses("empty compact")}><h3>No stock-ready orders</h3></div> : <div className={workspaceClasses("suggestion-grid")}>
          {suggestions.ready_orders.map(order => <article className={workspaceClasses("suggestion-card ready")} key={order.order_id} data-testid={`ready-order-${order.order_number}`}>
            <div><span className={workspaceClasses("parcel-kicker")}>FULL ORDER READY</span><h3>{order.order_number}</h3><p>{order.party_name} / {formatDate(order.date)}</p></div>
            <strong>{number(order.pieces)} pieces</strong>
            <Button variant="outline" onClick={() => navigate(`/orders/${order.order_id}`)}>Open<ArrowRight size={14} /></Button>
          </article>)}
          {suggestions.ready_parcels.map(group => group.parcels.map(parcel => <article className={workspaceClasses("suggestion-card")} key={`${group.order_id}-${parcel.parcel_index}`} data-testid={`ready-parcel-${group.order_number}-${parcel.parcel_index}`}>
            <div><span className={workspaceClasses("parcel-kicker")}>PARCEL {parcel.parcel_index + 1} READY</span><h3>{group.order_number}</h3><p>{group.party_name} / {formatDate(group.date)}</p></div>
            <strong>{number(parcel.parcel_pieces)} pieces</strong>
            <Button variant="outline" onClick={() => navigate(`/orders/${group.order_id}`)}>Open<ArrowRight size={14} /></Button>
          </article>))}
          {suggestions.partial_parcels.map(parcel => <article className={workspaceClasses("suggestion-card partial")} key={`${parcel.order_id}-${parcel.parcel_index}`} data-testid={`partial-parcel-${parcel.order_number}-${parcel.parcel_index}`}>
            <div><span className={workspaceClasses("parcel-kicker")}>PARTIAL STOCK</span><h3>{parcel.order_number} parcel {parcel.parcel_index + 1}</h3><p>{parcel.items.filter(item => item.available_pieces > 0).map(item => `${item.catalogue_name} ${item.volume_name}: ${number(item.available_pieces)}`).join(' / ')}</p></div>
            <CheckCircle2 size={18} />
            <Button variant="outline" onClick={() => navigate(`/orders/${parcel.order_id}`)}>Open<ArrowRight size={14} /></Button>
          </article>)}
        </div>}
      </section>
      <div className={workspaceClasses("toolbar filters")}><div className={workspaceClasses("search")}><Search size={17} /><input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Search catalogue or volume" data-testid="pending-search-input" /></div><select value={cat} onChange={e => { setCat(e.target.value); setPage(1); }} data-testid="pending-catalogue-filter"><option value="">All catalogues</option>{cats.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></div>
      {!rows.length ? <div className={workspaceClasses("empty")} data-testid="pending-empty"><h3>{query || cat ? 'No matching requirements' : 'Nothing pending'}</h3></div> : <div className={workspaceClasses("table-wrap")}><table className={workspaceClasses("responsive-table")}><thead><tr>{['Catalogue', 'Volume', 'Pieces / set', 'Pending sets', 'Pending pieces'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={`${r.catalogue_id}-${r.volume_id}`} data-testid={`pending-row-${r.catalogue_id}-${r.volume_id}`}><td data-label="Catalogue"><strong>{r.catalogue_name}</strong></td><td data-label="Volume">{r.volume_name}</td><td data-label="Pieces / set">{r.pieces_per_set}</td><td data-label="Pending sets"><strong>{number(r.sets)}</strong></td><td data-label="Pending pieces"><strong>{number(r.pieces)}</strong></td></tr>)}</tbody></table></div>}<Pagination {...data} onChange={setPage} busy={loading} label="requirements"/>
    </>}
  </div>;
}
