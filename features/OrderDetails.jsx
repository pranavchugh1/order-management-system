"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from "@/lib/navigation";
import { ArrowLeft, Pencil, Send, X } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { formatDate } from '@/lib/dates';
const FIRM_KEY = 'aditya-last-firm';
const CHALLAN_KEY = 'aditya-last-challan';
function nextChallanNumber(value) {
  const text = (value || '').trim();
  const match = text.match(/^(.*?)(\d+)$/);
  if (!match) return '';
  const [, prefix, digits] = match;
  const next = String(Number(digits) + 1).padStart(digits.length, '0');
  return `${prefix}${next}`;
}
export default function OrderDetails() {
  const {
      id
    } = useParams(),
    navigate = useNavigate();
  const [order, setOrder] = useState(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const [firms, setFirms] = useState([]),
    [dialog, setDialog] = useState(null);
  useEffect(() => {
    api.get(`/orders/${id}`).then(r => setOrder(r.data)).catch(e => setError(errorText(e)));
  }, [id]);
  useEffect(() => {
    api.get('/firms').then(r => setFirms(r.data.firms)).catch(() => {});
  }, []);
  const openDialog = i => {
    let lastFirm = '';
    let lastChallan = '';
    try {
      lastFirm = sessionStorage.getItem(FIRM_KEY) || '';
      lastChallan = sessionStorage.getItem(CHALLAN_KEY) || '';
    } catch (_) {}
    setDialog({
      index: i,
      challan: nextChallanNumber(lastChallan),
      firm: firms.includes(lastFirm) ? lastFirm : firms[0] || ''
    });
  };
  const confirm = async () => {
    const challan = dialog.challan.trim();
    if (!challan || !dialog.firm) {
      setError('Challan number and firm are required');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const r = await api.patch(`/orders/${id}/parcels/${dialog.index}`, {
        version: order.version,
        challan_number: challan,
        firm: dialog.firm
      });
      setOrder(r.data);
      try {
        sessionStorage.setItem(FIRM_KEY, dialog.firm);
        sessionStorage.setItem(CHALLAN_KEY, challan);
      } catch (_) {}
      setDialog(null);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return <div className={workspaceClasses("page")}><button className={workspaceClasses("back-link")} onClick={() => navigate(-1)} data-testid="details-back-button"><ArrowLeft size={16} />Back</button>
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="order-details-error">{error}</div>}
    {!order ? !error && <div className={workspaceClasses("loading")} data-testid="order-details-loading">Loading order…</div> : <>
      <PageTitle eyebrow={order.order_number} title={order.party_name} description={<span data-testid="order-detail-date">{formatDate(order.date)} · {order.parcels.length} parcels{order.remarks ? ` · ${order.remarks}` : ''}</span>} action={<Button variant="outline" onClick={() => navigate(`/orders/${id}/edit`)} data-testid="edit-order-button"><Pencil size={15} />Edit order</Button>} />
      <div className={workspaceClasses("details-status")}><span className={workspaceClasses(`status ${order.status === 'Completed' ? 'sent' : ''}`)} data-testid="order-detail-status">{order.status}</span><strong data-testid="order-detail-total">{number(order.total_pieces)} pieces</strong></div>
      <div className={workspaceClasses("details-grid")}>{order.parcels.map((p, i) => <section className={workspaceClasses("detail-parcel")} key={i}><div className={workspaceClasses("detail-parcel-head")}><div><span className={workspaceClasses("parcel-kicker")}>PARCEL {i + 1}</span><h2>{number(p.target)} pieces</h2></div><span className={workspaceClasses(`status ${p.status === 'Parcel Sent' ? 'sent' : ''}`)} data-testid={`parcel-${i}-status`}>{p.status}</span></div>
        <div className={workspaceClasses("detail-rows")}>{p.compositions.map((c, j) => <div className={workspaceClasses("detail-row")} key={j} data-testid={`parcel-${i}-item-${j}`}><span>{c.catalogue_name} <b>{c.volume_name}</b></span><span>{c.pieces_per_set} × {c.sets} sets</span><strong>{number(c.pieces_per_set * c.sets)}</strong></div>)}</div>
        {p.status === 'Parcel Sent' && (p.challan_number || p.firm) && <div className={workspaceClasses("challan-strip")} data-testid={`parcel-${i}-challan`}><span>Challan <b>{p.challan_number || '—'}</b></span><span>Firm <b>{p.firm || '—'}</b></span>{p.sent_at && <span data-testid={`parcel-${i}-sent-date`}>Sent <b>{formatDate(p.sent_at)}</b></span>}</div>}
        <div className={workspaceClasses("detail-total")}><span>Total <b data-testid={`parcel-${i}-total-pieces`}>{number(p.total)} pieces</b></span>{p.status !== 'Parcel Sent' && <Button disabled={busy} onClick={() => openDialog(i)} data-testid={`parcel-${i}-sent-button`}><Send size={15} />Parcel sent</Button>}</div>
      </section>)}</div>
    </>}
    {dialog && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" aria-labelledby="challan-heading" onClick={e => {
      if (e.target === e.currentTarget && !busy) setDialog(null);
    }} data-testid="challan-dialog">
      <div className={workspaceClasses("modal-card")}><header className={workspaceClasses("modal-head")}><h2 id="challan-heading">Dispatch parcel {dialog.index + 1}</h2><button className={workspaceClasses("icon-button")} onClick={() => !busy && setDialog(null)} aria-label="Close" data-testid="challan-dialog-close"><X size={16} /></button></header>
        <div className={workspaceClasses("modal-body")}>
          <label>Challan number<input autoFocus value={dialog.challan} maxLength={60} onChange={e => setDialog(d => ({
              ...d,
              challan: e.target.value
            }))} data-testid="challan-number-input" placeholder="e.g. CH-2401" /></label>
          <label>Firm<select value={dialog.firm} onChange={e => setDialog(d => ({
              ...d,
              firm: e.target.value
            }))} data-testid="challan-firm-select">{firms.map(f => <option key={f} value={f}>{f}</option>)}</select></label>
          <p className={workspaceClasses("modal-hint")}>Firm and challan number remembered for the next dispatch.</p>
        </div>
        <footer className={workspaceClasses("modal-foot")}><Button variant="outline" onClick={() => setDialog(null)} disabled={busy} data-testid="challan-dialog-cancel">Cancel</Button><Button onClick={confirm} disabled={busy || !dialog.challan.trim() || !dialog.firm} data-testid="challan-dialog-confirm"><Send size={15} />{busy ? 'Sending…' : 'Confirm dispatch'}</Button></footer>
      </div></div>}
  </div>;
}
