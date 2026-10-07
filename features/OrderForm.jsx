"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from "@/lib/navigation";
import { ArrowLeft, Check, Plus } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { OrderEditor } from '@/components/OrderEditor';
import { blankParcel, orderPayload, validOrder } from '@/components/ParcelEditor';
import { api, errorText } from '@/lib/api';
import { useMasters } from '@/hooks/useMasters';
import { todayISO } from '@/lib/dates';
export default function OrderForm({
  existing = false
}) {
  const {
      id
    } = useParams(),
    navigate = useNavigate();
  const masters = useMasters();
  const [order, setOrder] = useState({
    party_id: '',
    party_name: '',
    parcels: [blankParcel()],
    remarks: '',
    date: todayISO()
  });
  const [loading, setLoading] = useState(existing),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const [showParty, setShowParty] = useState(false),
    [partyForm, setPartyForm] = useState({
      name: '',
      agent: '',
      transport: ''
    }),
    [partyError, setPartyError] = useState('');
  useEffect(() => {
    if (existing) api.get(`/orders/${id}`).then(r => setOrder(r.data)).catch(e => setError(errorText(e))).finally(() => setLoading(false));
  }, [existing, id]);
  const save = async () => {
    if (!validOrder(order)) return setError('Select a party and match every parcel to its target.');
    setBusy(true);
    setError('');
    try {
      const r = await (existing ? api.put(`/orders/${id}`, orderPayload(order)) : api.post('/orders', orderPayload(order)));
      navigate(`/orders/${r.data.id}`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const addParty = async e => {
    e.preventDefault();
    setBusy(true);
    setPartyError('');
    try {
      const r = await api.post('/parties', partyForm);
      masters.setParties(p => [...p, r.data]);
      setOrder(o => ({
        ...o,
        party_id: r.data.id,
        party_name: r.data.name
      }));
      setShowParty(false);
      setPartyForm({
        name: '',
        agent: '',
        transport: ''
      });
    } catch (e) {
      setPartyError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return <div className={workspaceClasses("page form-page")}><button className={workspaceClasses("back-link")} onClick={() => navigate(existing ? `/orders/${id}` : '/')} data-testid="order-form-back-button"><ArrowLeft size={16} />Back to orders</button>
    <PageTitle eyebrow={existing ? 'EDIT ORDER' : 'NEW ORDER'} title={existing ? 'Edit order' : 'Create an order'} description="Customer details & parcel composition" action={<Button disabled={busy || loading || masters.loading || !validOrder(order)} onClick={save} data-testid="save-order-button"><Check size={17} />{busy ? 'Saving…' : existing ? 'Save changes' : 'Save order'}</Button>} />
    {(error || masters.error) && <div className={workspaceClasses("error-banner")} role="alert" data-testid="order-form-error">{error || masters.error}</div>}
    {loading || masters.loading ? <div className={workspaceClasses("loading")} data-testid="order-form-loading">Loading order…</div> : <fieldset className={workspaceClasses("editor-fieldset")} disabled={busy}><button className={workspaceClasses("add-inline")} disabled={order.parcels.some(p => p.status === 'Parcel Sent')} onClick={() => setShowParty(true)} data-testid="add-new-party-button"><Plus size={15} />New party</button><OrderEditor order={order} onChange={setOrder} parties={masters.parties} catalogues={masters.catalogues} /></fieldset>}
    <Dialog open={showParty} onOpenChange={setShowParty}><DialogContent data-testid="add-party-modal"><DialogHeader><DialogTitle>Add new party</DialogTitle></DialogHeader><form onSubmit={addParty}><label>Party name<input autoFocus value={partyForm.name} onChange={e => setPartyForm({
              ...partyForm,
              name: e.target.value
            })} maxLength={120} required data-testid="new-party-name-input" /></label><label>Agent<input value={partyForm.agent} onChange={e => setPartyForm({
              ...partyForm,
              agent: e.target.value
            })} maxLength={120} data-testid="new-party-agent-input" /></label><label>Transport<input value={partyForm.transport} onChange={e => setPartyForm({
              ...partyForm,
              transport: e.target.value
            })} maxLength={120} data-testid="new-party-transport-input" /></label>{partyError && <div className={workspaceClasses("error-banner")} role="alert" data-testid="new-party-error">{partyError}</div>}<Button type="submit" disabled={busy} data-testid="save-new-party-button">Add party</Button></form></DialogContent></Dialog>
  </div>;
}
