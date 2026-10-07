"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useMemo, useState } from 'react';
import { Link } from "@/lib/navigation";
import { ArrowRight, Check, ChevronDown, Eye, Plus, RotateCcw, Trash2 } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';
import { useMasters } from '@/hooks/useMasters';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { OrderEditor } from '@/components/OrderEditor';
import { orderPayload, parcelTotal, validOrder } from '@/components/ParcelEditor';
import { BulkParcelBuilder } from '@/components/BulkParcelBuilder';
import { todayISO } from '@/lib/dates';
const emptyBlock = () => ({
  id: crypto.randomUUID(),
  party_id: '',
  text: '',
  remarks: ''
});
export default function BulkOrders() {
  const {
      user
    } = useAuth(),
    masters = useMasters();
  const storageKey = `bulk-draft-${user.id}`;
  const [draft, setDraft] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(storageKey)) || {
        blocks: [emptyBlock()],
        orders: [],
        errors: [],
        stale: true,
        submission: null
      };
    } catch (_) {
      return {
        blocks: [emptyBlock()],
        orders: [],
        errors: [],
        stale: true,
        submission: null
      };
    }
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [expanded, setExpanded] = useState(0),
    [receipt, setReceipt] = useState(null);
  const {
    blocks,
    orders,
    errors,
    stale,
    submission
  } = draft;
  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(draft));
    } catch (_) {}
  }, [draft, storageKey]);
  useEffect(() => {
    const guard = e => {
      if (blocks.some(b => b.party_id || b.text.trim()) || orders.length) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [blocks, orders.length]);
  const totals = useMemo(() => orders.reduce((sum, o) => {
    for (const p of o.parcels) {
      sum.parcels++;
      sum.pieces += parcelTotal(p);
      sum.rows += p.compositions.length;
      for (const c of p.compositions) sum.sets += Number(c.sets || 0);
    }
    return sum;
  }, {
    parcels: 0,
    sets: 0,
    pieces: 0,
    rows: 0
  }), [orders]);
  const valid = !stale && !errors.length && orders.length > 0 && orders.length <= 50 && totals.parcels <= 500 && totals.rows <= 2000 && orders.every(validOrder);
  const readyToPreview = blocks.some(b => b.party_id && b.text.trim());
  const setBlock = (i, change) => setDraft(d => ({
    ...d,
    blocks: d.blocks.map((b, j) => i === j ? {
      ...b,
      ...change
    } : b),
    stale: true
  }));
  const removeBlock = i => setDraft(d => ({
    ...d,
    blocks: d.blocks.length > 1 ? d.blocks.filter((_, j) => i !== j) : [emptyBlock()],
    stale: true
  }));
  const addBlock = () => setDraft(d => ({
    ...d,
    blocks: [...d.blocks, emptyBlock()],
    stale: true
  }));
  const appendLine = (i, line) => {
    const text = [blocks[i].text.trimEnd(), line].filter(Boolean).join('\n');
    if (text.length > 10000) {
      setError('This party block has reached the 10,000-character limit.');
      return false;
    }
    setBlock(i, {
      text
    });
    setError('');
    return true;
  };
  const updateOrder = (i, order) => setDraft(d => ({
    ...d,
    orders: d.orders.map((o, j) => i === j ? order : o)
  }));
  const preview = async () => {
    const active = blocks.filter(b => b.party_id || b.text.trim() || b.remarks.trim());
    if (active.some(b => !b.party_id || !b.text.trim())) {
      setError('Select a party and add parcel lines in every non-empty block.');
      return;
    }
    const payload = {
      blocks: active.map(b => ({
        party_id: b.party_id,
        text: b.text,
        remarks: b.remarks || ''
      }))
    };
    if (!payload.blocks.length) {
      setError('Add at least one party with parcels.');
      return;
    }
    if (orders.length && !window.confirm('Rebuild the preview? Current preview edits will be replaced.')) return;
    setBusy(true);
    setError('');
    setReceipt(null);
    try {
      const r = await api.post('/bulk/preview', payload);
      setDraft(d => ({
        ...d,
        orders: r.data.orders.map(o => ({
          ...o,
          date: todayISO()
        })),
        errors: r.data.errors,
        stale: false,
        submission: null
      }));
      setExpanded(0);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const commit = async () => {
    if (!submission && !window.confirm(`Create all ${orders.length} orders with ${totals.parcels} parcels?`)) return;
    const payload = submission || {
      request_id: crypto.randomUUID(),
      orders: orders.map(orderPayload)
    };
    const saved = {
      ...draft,
      submission: payload
    };
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(saved));
    } catch (_) {}
    setDraft(saved);
    setBusy(true);
    setError('');
    try {
      const r = await api.post('/bulk/commit', payload);
      setReceipt(r.data);
      setDraft({
        blocks: [emptyBlock()],
        orders: [],
        errors: [],
        stale: true,
        submission: null
      });
    } catch (e) {
      setError(errorText(e));
      const status = e.response?.status;
      if (status && status < 500 && !(status === 409 && errorText(e).includes('being saved')) && status !== 429) setDraft(d => ({
        ...d,
        submission: null
      }));
    } finally {
      setBusy(false);
    }
  };
  return <div className={workspaceClasses("page bulk-page")}><PageTitle eyebrow="WORKSPACE / BULK ENTRY" title="Many orders. One go." description="Pick a party. Type its parcels. Add another." action={<Button disabled={busy || masters.loading || !valid && !submission} onClick={commit} data-testid="bulk-save-button"><Check size={17} />{busy ? 'Working…' : submission ? 'Retry saved batch' : `Create ${orders.length || ''} orders`}</Button>} />
    {(error || masters.error) && <div className={workspaceClasses("error-banner")} role="alert" data-testid="bulk-error">{error || masters.error}</div>}
    {receipt && <div className={workspaceClasses("bulk-success")} role="status" data-testid="bulk-success"><Check size={22} /><div><h2>{receipt.count} orders created</h2><div className={workspaceClasses("receipt-links")}>{receipt.orders.map(o => <Link to={`/orders/${o.id}`} key={o.id} data-testid={`bulk-created-${o.id}`}>{o.order_number} · {o.party_name}<ArrowRight size={13} /></Link>)}</div></div></div>}
    {submission && <div className={workspaceClasses("notice")} data-testid="bulk-retry-notice">This preview is locked while its save is being confirmed. Retry the same batch safely.</div>}
    <section className={workspaceClasses("bulk-input-section")}><div className={workspaceClasses("section-label")}><span>01</span><div><h2>Party blocks</h2><p>Up to 50 parties · 500 parcels total</p></div></div>
      <div className={workspaceClasses("bulk-blocks")} data-testid="bulk-blocks">
        {blocks.map((b, i) => <div key={b.id || i} className={workspaceClasses("bulk-block")} data-testid={`bulk-block-${i}`}>
          <div className={workspaceClasses("bulk-block-head")}><span className={workspaceClasses("parcel-kicker")}>PARTY {String(i + 1).padStart(2, '0')}</span>
            {blocks.length > 1 && <button type="button" className={workspaceClasses("icon-button danger-icon")} disabled={busy || !!submission} title="Remove party block" onClick={() => removeBlock(i)} data-testid={`bulk-block-${i}-remove`}><Trash2 size={16} /></button>}
          </div>
          <label className={workspaceClasses("bulk-block-party")}>Party
            <select value={b.party_id} disabled={busy || !!submission || masters.loading} onChange={e => setBlock(i, {
              party_id: e.target.value
            })} data-testid={`bulk-block-${i}-party-select`}>
              <option value="">Select a party</option>
              {masters.parties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <BulkParcelBuilder catalogues={masters.catalogues} prefix={`bulk-block-${i}`} disabled={busy || !!submission || masters.loading} onAppend={line => appendLine(i, line)} />
          <label className={workspaceClasses("bulk-block-parcels")}>Parcel lines
            <textarea rows={3} maxLength={10000} disabled={busy || !!submission} value={b.text} spellCheck={false} onChange={e => setBlock(i, {
              text: e.target.value
            })} placeholder={'Saya 1 + Siya 2 1 parcel\nSaya 1 & Siya 2 1 parcel @ 76 pcs'} data-testid={`bulk-block-${i}-text-input`} />
          </label>
          <label className={workspaceClasses("bulk-block-remarks")}>Remarks (optional)
            <input value={b.remarks} maxLength={1000} disabled={busy || !!submission} onChange={e => setBlock(i, {
              remarks: e.target.value
            })} placeholder="Notes for this party's order" data-testid={`bulk-block-${i}-remarks-input`} />
          </label>
        </div>)}
      </div>
      <div className={workspaceClasses("bulk-input-footer")}>
        <div className={workspaceClasses("bulk-hints")}><span data-testid="bulk-size-rules">Default parcel: 72 pieces · All 10-pc sets: 80 pieces</span></div>
        <div className={workspaceClasses("bulk-input-actions")}>
          <Button variant="outline" disabled={busy || !!submission || blocks.length >= 50} onClick={addBlock} data-testid="bulk-add-block-button"><Plus size={16} />Add another party</Button>
          <Button variant="outline" disabled={!readyToPreview || busy || !!submission} onClick={preview} data-testid="bulk-preview-button"><Eye size={16} />Preview orders</Button>
        </div>
      </div>
    </section>
    {errors.length > 0 && <div className={workspaceClasses("error-banner")} data-testid="bulk-parse-errors"><strong>{errors.length} entries need attention</strong>{errors.map((e, i) => <div className={workspaceClasses("parse-error")} key={i} data-testid={`bulk-line-error-${i}`}><b>{e.block ? `Block ${e.block}${e.party_name ? ` · ${e.party_name}` : ''}${e.line ? ` · Line ${e.line}` : ''}` : 'Order'}: {e.text}</b><span>{e.message}</span></div>)}</div>}
    {!!orders.length && <section className={workspaceClasses("bulk-preview-section")}><div className={workspaceClasses("section-label")}><span>02</span><div><h2>Review orders</h2><p data-testid="bulk-summary">{orders.length} orders · {number(totals.parcels)} parcels · {number(totals.sets)} sets · {number(totals.pieces)} pieces</p></div></div>
      {stale && <div className={workspaceClasses("notice")} data-testid="bulk-stale-notice">Blocks changed. Generate a fresh preview before saving.</div>}
      {totals.parcels > 500 && <div className={workspaceClasses("error-banner")} data-testid="bulk-limit-error">Remove parcels to stay within the 500-parcel batch limit.</div>}
      {totals.rows > 2000 && <div className={workspaceClasses("error-banner")} data-testid="bulk-composition-limit-error">Remove items to stay within the 2,000-item batch limit.</div>}
      <fieldset className={workspaceClasses("editor-fieldset")} disabled={busy || !!submission}>{orders.map((o, i) => <section className={workspaceClasses("bulk-order")} key={i} data-testid={`bulk-order-${i}`}><div className={workspaceClasses("bulk-order-head")}><button type="button" className={workspaceClasses("bulk-order-toggle")} onClick={() => setExpanded(expanded === i ? -1 : i)} aria-expanded={expanded === i} data-testid={`bulk-order-${i}-toggle`}><span className={workspaceClasses("parcel-kicker")}>{String(i + 1).padStart(2, '0')}</span><strong>{o.party_name || 'Select a party'}</strong><span className={workspaceClasses(`status ${validOrder(o) ? 'sent' : ''}`)} data-testid={`bulk-order-${i}-validation`}>{validOrder(o) ? `${o.parcels.length} parcels · Ready` : 'Needs attention'}</span><ChevronDown size={17} /></button><button type="button" className={workspaceClasses("icon-button danger-icon")} title="Remove order" onClick={() => setDraft(d => ({
              ...d,
              orders: d.orders.filter((_, j) => i !== j)
            }))} data-testid={`bulk-order-${i}-remove`}><Trash2 size={16} /></button></div>
        {expanded === i && <OrderEditor order={o} onChange={value => updateOrder(i, value)} parties={masters.parties} catalogues={masters.catalogues} prefix={`bulk-order-${i}`} />}
      </section>)}</fieldset>
      <div className={workspaceClasses("bulk-save-footer")}><Button variant="outline" disabled={busy || !!submission} onClick={() => {
          if (window.confirm('Discard this preview and its edits?')) setDraft(d => ({
            ...d,
            orders: [],
            errors: [],
            stale: true
          }));
        }} data-testid="bulk-discard-button"><RotateCcw size={15} />Discard preview</Button><Button disabled={busy || masters.loading || !valid && !submission} onClick={commit} data-testid="bulk-confirm-button"><Check size={16} />{submission ? 'Retry saved batch' : `Create ${orders.length} orders`}</Button></div>
    </section>}
    <Dialog open={showParty} onOpenChange={setShowParty}><DialogContent data-testid="bulk-add-party-modal"><DialogHeader><DialogTitle>Add new party</DialogTitle></DialogHeader><form onSubmit={addParty}><label>Party name<input autoFocus value={partyForm.name} onChange={e => setPartyForm({
              ...partyForm,
              name: e.target.value
            })} maxLength={120} required data-testid="bulk-new-party-name-input" /></label><label>Agent<input value={partyForm.agent} onChange={e => setPartyForm({
              ...partyForm,
              agent: e.target.value
            })} maxLength={120} data-testid="bulk-new-party-agent-input" /></label><label>Transport<input value={partyForm.transport} onChange={e => setPartyForm({
              ...partyForm,
              transport: e.target.value
            })} maxLength={120} data-testid="bulk-new-party-transport-input" /></label>{partyError && <div className={workspaceClasses("error-banner")} role="alert" data-testid="bulk-new-party-error">{partyError}</div>}<Button type="submit" disabled={busy} data-testid="bulk-save-new-party-button">Add party</Button></form></DialogContent></Dialog>
  </div>;
}
