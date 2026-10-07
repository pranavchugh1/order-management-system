"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { Plus } from 'lucide-react';
import { ParcelEditor, blankParcel } from './ParcelEditor';
import { Button } from './WorkspacePrimitives';
import { DateInput } from './DateInput';
export const OrderEditor = ({
  order,
  onChange,
  parties,
  catalogues,
  prefix = 'order'
}) => {
  const sent = order.parcels.some(p => p.status === 'Parcel Sent');
  const selectedParty = parties.find(p => p.id === order.party_id);
  return <div data-testid={`${prefix}-editor`}>
    <div className={workspaceClasses("order-editor-basics")}>
      <label>Party<select disabled={sent} value={order.party_id} onChange={e => {
          const p = parties.find(p => p.id === e.target.value);
          onChange({
            ...order,
            party_id: p?.id || '',
            party_name: p?.name || ''
          });
        }} data-testid={`${prefix}-party-select`}><option value="">Select a party</option>{parties.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
      <label>Order date<DateInput value={order.date || ''} onChange={date => onChange({
          ...order,
          date
        })} testId={`${prefix}-date-input`} /></label>
      <label>Remarks<input value={order.remarks || ''} maxLength={1000} onChange={e => onChange({
          ...order,
          remarks: e.target.value
        })} data-testid={`${prefix}-remarks-input`} /></label>
    </div>
    {selectedParty && (selectedParty.agent || selectedParty.transport) && <div className={workspaceClasses("party-meta")} data-testid={`${prefix}-party-meta`}>{selectedParty.agent && <span>Agent <b>{selectedParty.agent}</b></span>}{selectedParty.transport && <span>Transport <b>{selectedParty.transport}</b></span>}</div>}
    {order.parcels.map((parcel, i) => <ParcelEditor key={i} parcel={parcel} index={i} catalogues={catalogues} prefix={`${prefix}-parcel`} onChange={p => onChange({
      ...order,
      parcels: order.parcels.map((old, j) => i === j ? p : old)
    })} onRemove={order.parcels.length > 1 && !order.parcels.slice(i).some(p => p.status === 'Parcel Sent') ? () => onChange({
      ...order,
      parcels: order.parcels.filter((_, j) => i !== j)
    }) : null} />)}
    <Button variant="outline" disabled={order.parcels.length >= 100} onClick={() => onChange({
      ...order,
      parcels: [...order.parcels, blankParcel()]
    })} data-testid={`${prefix}-add-parcel-button`}><Plus size={16} />Add parcel</Button>
  </div>;
};
