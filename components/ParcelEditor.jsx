"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { Check, Plus, Trash2 } from 'lucide-react';
import { number } from '@/lib/api';
import { validDate } from '@/lib/dates';
export const blankRow = () => ({
  catalogue_id: '',
  catalogue_name: '',
  volume_id: '',
  volume_name: '',
  pieces_per_set: 0,
  sets: 1
});
export const blankParcel = () => ({
  target: 72,
  status: 'Pending',
  compositions: [blankRow()]
});
export const parcelTotal = p => p.compositions.reduce((sum, c) => sum + Number(c.pieces_per_set) * Number(c.sets), 0);
export const validOrder = o => Boolean(o.party_id && validDate(o.date) && o.parcels.length && o.parcels.length <= 100 && o.parcels.every(p => Number.isInteger(Number(p.target)) && Number(p.target) > 0 && Number(p.target) <= 1000000 && p.compositions.length && p.compositions.length <= 100 && p.compositions.every(c => c.catalogue_id && c.volume_id && Number.isInteger(Number(c.sets)) && Number(c.sets) > 0 && Number(c.sets) <= 100000) && parcelTotal(p) === Number(p.target)));
export const orderPayload = o => ({
  party_id: o.party_id,
  party_name: o.party_name,
  remarks: o.remarks || '',
  date: o.date || null,
  ...(o.version !== undefined ? {
    version: o.version
  } : {}),
  parcels: o.parcels.map(p => ({
    target: Number(p.target),
    status: p.status,
    compositions: p.compositions.map(c => ({
      catalogue_id: c.catalogue_id,
      catalogue_name: c.catalogue_name,
      volume_id: c.volume_id,
      volume_name: c.volume_name,
      pieces_per_set: Number(c.pieces_per_set),
      sets: Number(c.sets)
    }))
  }))
});
export const ParcelEditor = ({
  parcel,
  index,
  catalogues,
  onChange,
  onRemove,
  prefix = 'parcel'
}) => {
  const id = `${prefix}-${index}`,
    total = parcelTotal(parcel),
    remaining = Number(parcel.target) - total;
  const locked = parcel.status === 'Parcel Sent';
  const changeRow = (ci, change) => onChange({
    ...parcel,
    compositions: parcel.compositions.map((c, i) => ci === i ? {
      ...c,
      ...change
    } : c)
  });
  const pickCat = (ci, value) => {
    const cat = catalogues.find(c => c.id === value);
    changeRow(ci, {
      catalogue_id: value,
      catalogue_name: cat?.name || '',
      volume_id: '',
      volume_name: '',
      pieces_per_set: 0
    });
  };
  const pickVol = (ci, value) => {
    const vol = catalogues.find(c => c.id === parcel.compositions[ci].catalogue_id)?.volumes.find(v => v.id === value);
    changeRow(ci, {
      volume_id: value,
      volume_name: vol?.name || '',
      pieces_per_set: vol?.pieces_per_set || 0
    });
  };
  return <fieldset className={workspaceClasses("parcel-editor")} disabled={locked} data-testid={`${id}-editor`}>
    <div className={workspaceClasses("parcel-head")}><div><span className={workspaceClasses("parcel-kicker")}>PARCEL {index + 1}</span><h3>{locked ? 'Sent · locked' : 'Composition'}</h3></div><div className={workspaceClasses("target-field")}>
      <label>Target pieces<input type="number" min="1" max="1000000" value={parcel.target} onChange={e => onChange({
            ...parcel,
            target: e.target.value
          })} data-testid={`${id}-target-input`} /></label>
      {!locked && onRemove && <button type="button" className={workspaceClasses("icon-button danger-icon")} title="Remove parcel" onClick={onRemove} data-testid={`${id}-remove-button`}><Trash2 size={16} /></button>}
    </div></div>
    <div className={workspaceClasses("comp-header")}><span>Catalogue</span><span>Volume</span><span>Pieces / set</span><span>Sets</span><span>Total</span><span /></div>
    {parcel.compositions.map((c, ci) => <div className={workspaceClasses("comp-row")} key={ci}>
      <select aria-label="Catalogue" value={c.catalogue_id} onChange={e => pickCat(ci, e.target.value)} data-testid={`${id}-row-${ci}-catalogue-select`}><option value="">Choose catalogue</option>{catalogues.map(cat => <option key={cat.id} value={cat.id}>{cat.name}</option>)}</select>
      <select aria-label="Volume" value={c.volume_id} onChange={e => pickVol(ci, e.target.value)} disabled={locked || !c.catalogue_id} data-testid={`${id}-row-${ci}-volume-select`}><option value="">Choose volume</option>{(catalogues.find(cat => cat.id === c.catalogue_id)?.volumes || []).map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select>
      <div className={workspaceClasses("auto-value")} data-testid={`${id}-row-${ci}-pieces-value`}>{c.pieces_per_set || '—'}</div>
      <input aria-label="Sets" type="number" min="1" max="100000" value={c.sets} onChange={e => changeRow(ci, {
        sets: e.target.value
      })} data-testid={`${id}-row-${ci}-sets-input`} />
      <div className={workspaceClasses("row-total")} data-testid={`${id}-row-${ci}-total`}>{number(c.pieces_per_set * c.sets)}</div>
      <button type="button" className={workspaceClasses("icon-button")} title="Remove composition" disabled={locked || parcel.compositions.length === 1} onClick={() => onChange({
        ...parcel,
        compositions: parcel.compositions.filter((_, i) => i !== ci)
      })} data-testid={`${id}-row-${ci}-remove-button`}><Trash2 size={15} /></button>
    </div>)}
    {!locked && <button type="button" className={workspaceClasses("add-row")} disabled={parcel.compositions.length >= 100} onClick={() => onChange({
      ...parcel,
      compositions: [...parcel.compositions, blankRow()]
    })} data-testid={`${id}-add-composition-button`}><Plus size={14} />Add catalogue / volume</button>}
    <div className={workspaceClasses(`parcel-total ${remaining === 0 ? 'complete' : remaining < 0 ? 'over' : ''}`)}><div><span>Parcel total</span><strong data-testid={`${id}-total`}>{number(total)} <small>/ {number(parcel.target)} pieces</small></strong></div><div className={workspaceClasses("parcel-state")} data-testid={`${id}-validation`}>{remaining === 0 ? <><Check size={16} />Matched</> : remaining > 0 ? `${number(remaining)} pieces remaining` : `${number(-remaining)} pieces over`}</div></div>
  </fieldset>;
};
