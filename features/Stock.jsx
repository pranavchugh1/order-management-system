"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useMemo, useState } from 'react';
import { Plus, RefreshCw, Search, X } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { formatDate } from '@/lib/dates';
import { useAuth } from '@/context/AuthContext';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { Pagination } from '@/components/Pagination';
import { getMasterOptions } from '@/lib/master-options';
const emptyStock = {
  catalogue_id: '',
  volume_id: '',
  sets: 0,
  pieces: 0,
  note: ''
};
const emptyEdit = {
  sets: 0,
  pieces: 0,
  note: ''
};
function movementTitle(row) {
  if (row.source === 'dispatch') return `Dispatch ${row.order_number || ''}`.trim();
  if (row.source === 'manual_add') return 'Stock added';
  if (row.source === 'opening_ready') return 'Opening ready stock';
  if (row.source === 'issue') return `${row.from_stage} to ${row.to_stage}`;
  return row.source || 'Stock movement';
}
export default function Stock() {
  const {
    user
  } = useAuth();
  const [catalogues, setCatalogues] = useState([]);
  const [data, setData] = useState({
    summary: [],
    movements: []
  });
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1), [movementPage, setMovementPage] = useState(1);
  const [saveKey, setSaveKey] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(emptyStock);
  const [edit, setEdit] = useState(null);
  const selectedCatalogue = catalogues.find(c => c.id === form.catalogue_id);
  const selectedVolume = selectedCatalogue?.volumes?.find(v => v.id === form.volume_id);
  const calculatedPieces = Number(form.sets || 0) * Number(selectedVolume?.pieces_per_set || 0) + Number(form.pieces || 0);
  const rows = data.summary || [];
  const totals = data.totals || { available_sets: 0, pending_sets: 0 };
  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [stock, cats] = await Promise.all([api.get('/stock', { params: { q: query, page, movement_page: movementPage } }), getMasterOptions('catalogues')]);
      setData(stock.data);
      setCatalogues(cats);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { const timer = setTimeout(load, 200); return () => clearTimeout(timer); }, [query, page, movementPage]);
  const setCatalogue = id => setForm({
    ...form,
    catalogue_id: id,
    volume_id: ''
  });
  const addStock = async e => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.post('/stock/add', {
        ...form,
        request_id: saveKey,
        sets: Number(form.sets || 0),
        pieces: Number(form.pieces || 0)
      });
      setForm(emptyStock);
      setShowAdd(false);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const openEdit = row => setEdit({
    row,
    request_id: crypto.randomUUID(),
    form: {
      sets: row.available_sets,
      pieces: row.available_pieces - row.available_sets * row.pieces_per_set,
      note: ''
    }
  });
  const saveBalance = async e => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.patch(`/stock/balances/${edit.row.catalogue_id}/${edit.row.volume_id}`, {
        request_id: edit.request_id,
        version: edit.row.version || 0,
        sets: Number(edit.form.sets || 0),
        pieces: Number(edit.form.pieces || 0),
        note: edit.form.note || ''
      });
      setEdit(null);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return <div className={workspaceClasses("page")}><PageTitle eyebrow="WORKSPACE / STOCK" title="Stock" description="Current sellable stock by catalogue volume with pending set demand." action={<div className={workspaceClasses("page-actions")}><Button variant="outline" onClick={load} disabled={loading || busy} data-testid="refresh-stock-button"><RefreshCw size={16} />Refresh</Button><Button onClick={() => { setSaveKey(crypto.randomUUID()); setShowAdd(true); }} data-testid="open-add-stock-button"><Plus size={16} />Add stock</Button></div>} />
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="stock-error">{error}</div>}
    {loading ? <div className={workspaceClasses("loading")} data-testid="stock-loading">Loading stock...</div> : <>
      <div className={workspaceClasses("summary-grid stock-summary")}>{[['available_sets', 'Available sets'], ['pending_sets', 'Pending sets']].map(([key, label]) => <div className={workspaceClasses("summary-stat")} key={key}><span>{label}</span><strong>{number(totals[key])}</strong></div>)}</div>
      <div className={workspaceClasses("toolbar")}><div className={workspaceClasses("search")}><Search size={17} /><input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Search catalogue or volume" data-testid="stock-search-input" /></div></div>
      <div className={workspaceClasses("table-wrap")}><table className={workspaceClasses("responsive-table")}><thead><tr>{['Catalogue', 'Volume', 'Pieces / set', 'Available sets', 'Pending sets', ...(user.role === 'admin' ? ['Admin'] : [])].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={`${row.catalogue_id}-${row.volume_id}`}><td data-label="Catalogue"><strong>{row.catalogue_name}</strong></td><td data-label="Volume">{row.volume_name}</td><td data-label="Pieces / set">{row.pieces_per_set}</td><td data-label="Available sets">{number(row.available_sets)}</td><td data-label="Pending sets">{number(row.pending_sets)}</td>{user.role === 'admin' && <td data-label="Admin"><Button variant="outline" onClick={() => openEdit(row)} disabled={busy}>Edit</Button></td>}</tr>)}</tbody></table></div><Pagination {...data} onChange={setPage} busy={loading} label="stock rows"/>
      <section className={workspaceClasses("stock-batches")}><div className={workspaceClasses("list-head")}><h2>Recent stock movements</h2><span>{data.movements.length} shown</span></div>{!data.movements.length ? <div className={workspaceClasses("empty compact")}><h3>No stock movements</h3></div> : <div className={workspaceClasses("movement-list stock-movement-list")}>{data.movements.map(row => <div key={row.id} data-testid={`stock-movement-${row.id}`}><strong>{movementTitle(row)}</strong><span>{row.catalogue_name} / {row.volume_name} / {number(Math.abs(row.ready_delta || row.pieces || 0))} pieces {Number(row.ready_delta || 0) < 0 ? 'out' : 'in'} / {formatDate(row.created_at)}{row.note ? ` / ${row.note}` : ''}</span></div>)}</div>}<Pagination {...data.movement_pagination} onChange={setMovementPage} busy={loading} label="movements"/></section>
    </>}
    {showAdd && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" onClick={e => {
      if (e.target === e.currentTarget && !busy) setShowAdd(false);
    }}><form className={workspaceClasses("modal-card stock-modal")} onSubmit={addStock}>
      <header className={workspaceClasses("modal-head")}><h2>Add stock</h2><button type="button" className={workspaceClasses("icon-button")} onClick={() => setShowAdd(false)}><X size={16} /></button></header>
      <div className={workspaceClasses("modal-body stock-form-grid")}>
        <label>Catalogue<select required value={form.catalogue_id} onChange={e => setCatalogue(e.target.value)} data-testid="stock-catalogue-select"><option value="">Select catalogue</option>{catalogues.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label>Volume<select required value={form.volume_id} disabled={!form.catalogue_id} onChange={e => setForm({
              ...form,
              volume_id: e.target.value
            })} data-testid="stock-volume-select"><option value="">Select volume</option>{(selectedCatalogue?.volumes || []).map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
        <label>Sets<input type="number" min="0" max="1000000" value={form.sets} onChange={e => setForm({
              ...form,
              sets: e.target.value
            })} data-testid="stock-sets-input" /></label>
        <label>Loose pieces<input type="number" min="0" max="10000000" value={form.pieces} onChange={e => setForm({
              ...form,
              pieces: e.target.value
            })} data-testid="stock-pieces-input" /></label>
        <label className={workspaceClasses("span-2")}>Note<input maxLength={300} value={form.note} onChange={e => setForm({
              ...form,
              note: e.target.value
            })} data-testid="stock-note-input" /></label>
        {selectedVolume && <div className={workspaceClasses("notice span-2")}>{selectedVolume.pieces_per_set} pieces per set. This entry will add {number(calculatedPieces)} pieces.</div>}
      </div>
      <footer className={workspaceClasses("modal-foot")}><Button variant="outline" type="button" onClick={() => setShowAdd(false)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy || !form.volume_id || calculatedPieces <= 0}>Add stock</Button></footer>
    </form></div>}
    {edit && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" onClick={e => {
      if (e.target === e.currentTarget && !busy) setEdit(null);
    }}><form className={workspaceClasses("modal-card")} onSubmit={saveBalance}>
      <header className={workspaceClasses("modal-head")}><h2>Edit stock balance</h2><button type="button" className={workspaceClasses("icon-button")} onClick={() => setEdit(null)}><X size={16} /></button></header>
      <div className={workspaceClasses("modal-body")}>
        <div className={workspaceClasses("notice")}>{edit.row.catalogue_name} / {edit.row.volume_name} / {edit.row.pieces_per_set} pieces per set</div>
        <label>Available sets<input type="number" min="-1000000" max="1000000" value={edit.form.sets} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                sets: e.target.value
              }
            })} data-testid="edit-stock-sets-input" /></label>
        <label>Loose pieces<input type="number" min="-10000000" max="10000000" value={edit.form.pieces} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                pieces: e.target.value
              }
            })} data-testid="edit-stock-pieces-input" /></label>
        <label>Reason<input maxLength={300} value={edit.form.note} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                note: e.target.value
              }
            })} data-testid="edit-stock-note-input" /></label>
      </div>
      <footer className={workspaceClasses("modal-foot")}><Button variant="outline" type="button" onClick={() => setEdit(null)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy}>Save balance</Button></footer>
    </form></div>}
  </div>;
}
