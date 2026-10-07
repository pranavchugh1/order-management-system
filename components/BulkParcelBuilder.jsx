"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useState } from 'react';
import { Plus, X } from 'lucide-react';
import { Button } from './WorkspacePrimitives';
export const BulkParcelBuilder = ({
  catalogues,
  prefix,
  disabled,
  onAppend
}) => {
  const [catalogueId, setCatalogueId] = useState(''),
    [volumeId, setVolumeId] = useState('');
  const [items, setItems] = useState([]),
    [quantity, setQuantity] = useState(1),
    [target, setTarget] = useState('');
  const catalogue = catalogues.find(c => c.id === catalogueId);
  const volume = catalogue?.volumes.find(v => v.id === volumeId);
  const current = volume ? {
    catalogueId,
    volumeId,
    catalogue: catalogue.name,
    volume: volume.name,
    piecesPerSet: volume.pieces_per_set
  } : null;
  const duplicate = current && items.some(i => i.catalogueId === catalogueId && i.volumeId === volumeId);
  const candidates = current && !duplicate ? [...items, current] : items;
  const sizes = candidates.map(item => item.piecesPerSet);
  const autoTarget = sizes.length && sizes.every(p => p === 10) ? 80 : sizes.length && sizes.every(p => p === 6 || p === 10) ? 72 : null;
  const effectiveTarget = target === '' ? autoTarget : Number(target);
  const equalUnit = sizes.length && sizes.every(p => p === sizes[0]) ? sizes[0] * sizes.length : null;
  const allocationError = !candidates.length ? '' : !effectiveTarget || !Number.isInteger(effectiveTarget) || effectiveTarget < 1 || effectiveTarget > 1000000 ? 'Enter a parcel size between 1 and 1,000,000 pieces.' : effectiveTarget < sizes.reduce((sum, size) => sum + size, 0) ? 'The parcel needs at least one whole set of every item.' : equalUnit && effectiveTarget % equalUnit ? `Equal sets need a parcel size divisible by ${equalUnit} pieces.` : equalUnit && effectiveTarget / equalUnit > 100000 ? 'Maximum 100,000 sets per item.' : '';
  const valid = candidates.length > 0 && candidates.length <= 100 && !allocationError && !duplicate && Number.isInteger(Number(quantity)) && quantity >= 1 && quantity <= 100;
  const quote = item => `"${`${item.catalogue} | ${item.volume}`.replaceAll('"', '""')}"`;
  const append = () => {
    const line = `${candidates.map(quote).join(' + ')} ${quantity} parcel${Number(quantity) === 1 ? '' : 's'}${target === '' ? '' : ` @ ${target} pcs`}`;
    if (onAppend(line) !== false) {
      setItems([]);
      setCatalogueId('');
      setVolumeId('');
    }
  };
  return <fieldset className={workspaceClasses("bulk-parcel-builder")} disabled={disabled} data-testid={`${prefix}-builder`}>
    <div className={workspaceClasses("bulk-picker-grid")}>
      <label>Catalogue<select value={catalogueId} onChange={e => {
          setCatalogueId(e.target.value);
          setVolumeId('');
        }} data-testid={`${prefix}-catalogue-select`}><option value="">Choose catalogue</option>{catalogues.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Volume<select value={volumeId} disabled={disabled || !catalogueId} onChange={e => setVolumeId(e.target.value)} data-testid={`${prefix}-volume-select`}><option value="">Choose volume</option>{(catalogue?.volumes || []).map(v => <option key={v.id} value={v.id}>{`${v.name} · ${v.pieces_per_set} pcs/set`}</option>)}</select></label>
      <Button variant="outline" disabled={disabled || !current || duplicate || items.length >= 99} onClick={() => {
        setItems([...items, current]);
        setCatalogueId('');
        setVolumeId('');
      }} data-testid={`${prefix}-mix-item-button`}><Plus size={15} />Mix another item</Button>
    </div>
    {!!items.length && <div className={workspaceClasses("bulk-mixed-items")} data-testid={`${prefix}-mixed-items`}>{items.map((item, i) => <span key={`${item.catalogueId}-${item.volumeId}`} data-testid={`${prefix}-mixed-item-${i}`}>{item.catalogue} · {item.volume}<button type="button" className={workspaceClasses("icon-button")} title="Remove mixed item" onClick={() => setItems(items.filter((_, j) => i !== j))} data-testid={`${prefix}-remove-item-${i}`}><X size={14} /></button></span>)}</div>}
    <div className={workspaceClasses("bulk-picker-quantity")}>
      <label>Parcels<input type="number" min="1" max="100" value={quantity} onChange={e => setQuantity(e.target.value)} data-testid={`${prefix}-quantity-input`} /></label>
      <label>Pieces / parcel<input type="number" min="1" max="1000000" value={target} onChange={e => setTarget(e.target.value)} placeholder="Auto" data-testid={`${prefix}-target-input`} /></label>
      <Button variant="outline" disabled={disabled || !valid} onClick={append} data-testid={`${prefix}-append-line-button`}><Plus size={15} />Add parcel line</Button>
    </div>
    {allocationError && <div className={workspaceClasses("field-error")} role="alert" data-testid={`${prefix}-allocation-error`}>{allocationError}</div>}
    {duplicate && <div className={workspaceClasses("field-error")} role="alert" data-testid={`${prefix}-duplicate-error`}>This catalogue/volume is already included. Choose a different item.</div>}
  </fieldset>;
};
