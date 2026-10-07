"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useCallback, useEffect, useState } from 'react';
import { api, errorText } from '@/lib/api';
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Button, PageTitle } from './WorkspacePrimitives';
import { Pagination } from '@/components/Pagination';
const emptyParty = {
  name: '',
  agent: '',
  transport: ''
};
export default function MasterManager({
  type
}) {
  const isCatalogue = type === 'catalogues';
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState(''), [page, setPage] = useState(1), [pagination, setPagination] = useState({}), [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [party, setParty] = useState(emptyParty);
  const [selected, setSelected] = useState(null);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState('');
  const [volume, setVolume] = useState({
    name: '',
    pieces_per_set: 6
  });
  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get(`/${type}`, { params: { q: query, page, page_size: 25 } }); setItems(r.data.items || []); setPagination(r.data); }
    catch (e) { setError(errorText(e)); }
    finally { setLoading(false); }
  }, [type, query, page]);
  useEffect(() => { const timer = setTimeout(load, 200); return () => clearTimeout(timer); }, [load]);
  const add = async () => {
    const payload = isCatalogue ? {
      name
    } : party;
    if (!payload.name.trim()) return;
    try {
      await api.post(`/${type}`, payload);
      setName('');
      setParty(emptyParty);
      load();
    } catch (e) {
      setError(errorText(e));
    }
  };
  const saveEdit = async () => {
    try {
      if (editing.kind === 'item') {
        const payload = isCatalogue ? {
          name: editing.name
        } : {
          name: editing.name,
          agent: editing.agent || '',
          transport: editing.transport || ''
        };
        await api.put(`/${type}/${editing.item.id}`, payload);
      } else {
        await api.put(`/catalogues/${editing.catalogue.id}/volumes/${editing.item.id}`, {
          name: editing.name,
          pieces_per_set: Number(editing.pieces)
        });
      }
      setEditing(null);
      load();
    } catch (e) {
      setError(errorText(e));
    }
  };
  const remove = async (item, kind, catalogueId) => {
    if (!window.confirm(`Delete ${item.name}?`)) return;
    try {
      await api.delete(kind === 'item' ? `/${type}/${item.id}` : `/catalogues/${catalogueId}/volumes/${item.id}`);
      if (kind === 'item') setSelected(null);
      load();
    } catch (e) {
      setError(errorText(e));
    }
  };
  const addVolume = async () => {
    if (!volume.name.trim() || !selected) return;
    try {
      await api.post(`/catalogues/${selected.id}/volumes`, {
        ...volume,
        pieces_per_set: Number(volume.pieces_per_set)
      });
      setVolume({
        name: '',
        pieces_per_set: 6
      });
      load();
    } catch (e) {
      setError(errorText(e));
    }
  };
  const currentSelected = items.find(item => item.id === selected?.id);
  return <div className={workspaceClasses("page")}><PageTitle eyebrow={`WORKSPACE / ${type.toUpperCase()}`} title={isCatalogue ? 'Catalogues' : 'Parties'} description={isCatalogue ? 'Set the volumes and pieces per set your team uses.' : 'Keep customer, agent, and transport details ready for order entry.'} />
    {error && <div className={workspaceClasses("error-banner")} data-testid="master-error">{error}<button className={workspaceClasses("icon-button")} onClick={() => setError('')} data-testid="dismiss-master-error"><X size={15} /></button></div>}
    <div className={workspaceClasses("master-layout")}>
      <section className={workspaceClasses("master-add")}><h2>{isCatalogue ? 'New catalogue' : 'New party'}</h2><p>{isCatalogue ? 'Start a catalogue, then add its volumes.' : 'Add customer routing details once and reuse them.'}</p>
        {isCatalogue ? <div className={workspaceClasses("input-action")}><input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Saya" data-testid={`new-${type}-name-input`} /><Button onClick={add} data-testid={`add-${type}-button`}><Plus size={16} /> Add</Button></div> : <div className={workspaceClasses("party-master-form")}>
          <label>Party name<input value={party.name} onChange={e => setParty({
              ...party,
              name: e.target.value
            })} placeholder="e.g. ABC Sarees" data-testid="new-parties-name-input" /></label>
          <label>Agent<input value={party.agent} onChange={e => setParty({
              ...party,
              agent: e.target.value
            })} placeholder="Agent name" data-testid="new-party-agent-input" /></label>
          <label>Transport<input value={party.transport} onChange={e => setParty({
              ...party,
              transport: e.target.value
            })} placeholder="Transport name" data-testid="new-party-transport-input" /></label>
          <Button onClick={add} data-testid={`add-${type}-button`}><Plus size={16} /> Add</Button>
        </div>}
      </section>
      <section className={workspaceClasses("master-list")}><div className={workspaceClasses("list-head")}><h2>{isCatalogue ? 'Catalogue library' : 'Party library'}</h2><span>{pagination.total || 0} total</span></div><input aria-label={`Search ${type}`} className="mb-4" placeholder={`Search ${type} by name…`} value={query} maxLength={120} onChange={e => { setQuery(e.target.value); setPage(1); }}/>{loading && <p className="py-3 text-xs text-muted-foreground">Loading…</p>}{items.map(item => <div className={workspaceClasses(`master-item ${currentSelected?.id === item.id ? 'selected' : ''}`)} key={item.id} onClick={() => isCatalogue && setSelected(item)} data-testid={`${type}-item-${item.id}`}>
        <div><div className={workspaceClasses("master-main")}><strong>{item.name}</strong>{isCatalogue ? <span>{item.volumes?.length || 0} volumes</span> : <span>{[item.agent, item.transport].filter(Boolean).join(' / ') || 'No agent or transport'}</span>}</div><div className={workspaceClasses("master-actions")}><button className={workspaceClasses("icon-button")} onClick={e => {
                e.stopPropagation();
                setEditing({
                  kind: 'item',
                  item,
                  name: item.name,
                  agent: item.agent || '',
                  transport: item.transport || ''
                });
              }} data-testid={`edit-${type}-${item.id}`} title="Edit"><Pencil size={14} /></button><button className={workspaceClasses("icon-button danger-icon")} onClick={e => {
                e.stopPropagation();
                remove(item, 'item');
              }} data-testid={`delete-${type}-${item.id}`} title="Delete"><Trash2 size={14} /></button></div></div>
        {isCatalogue && currentSelected?.id === item.id && <div className={workspaceClasses("volume-panel")}><div className={workspaceClasses("volume-list")}>{(item.volumes || []).map(v => <span key={v.id}>{v.name}<b>{v.pieces_per_set}/set</b><button className={workspaceClasses("icon-button")} onClick={e => {
                  e.stopPropagation();
                  setEditing({
                    kind: 'volume',
                    item: v,
                    catalogue: item,
                    name: v.name,
                    pieces: v.pieces_per_set
                  });
                }} data-testid={`edit-volume-${v.id}`}><Pencil size={12} /></button><button className={workspaceClasses("icon-button danger-icon")} onClick={e => {
                  e.stopPropagation();
                  remove(v, 'volume', item.id);
                }} data-testid={`delete-volume-${v.id}`}><Trash2 size={12} /></button></span>)}</div><div className={workspaceClasses("volume-add")}><input value={volume.name} onChange={e => setVolume({
                ...volume,
                name: e.target.value
              })} placeholder="Volume name" data-testid="new-volume-name-input" /><input type="number" min="1" value={volume.pieces_per_set} onChange={e => setVolume({
                ...volume,
                pieces_per_set: e.target.value
              })} data-testid="new-volume-pieces-input" /><Button onClick={addVolume} data-testid="add-volume-button"><Plus size={15} /> Add volume</Button></div></div>}
      </div>)}<Pagination {...pagination} onChange={setPage} busy={loading} label={type}/></section>
    </div>
    {editing && <div className={workspaceClasses("modal-backdrop")}><div className={workspaceClasses("modal")}><div className={workspaceClasses("modal-head")}><h2>Edit {editing.kind === 'volume' ? 'volume' : isCatalogue ? 'catalogue' : 'party'}</h2><button className={workspaceClasses("icon-button")} onClick={() => setEditing(null)} data-testid="close-master-edit"><X size={18} /></button></div><label>Name<input value={editing.name} onChange={e => setEditing({
            ...editing,
            name: e.target.value
          })} data-testid="master-edit-name-input" /></label>{editing.kind === 'item' && !isCatalogue && <><label>Agent<input value={editing.agent || ''} onChange={e => setEditing({
              ...editing,
              agent: e.target.value
            })} data-testid="master-edit-agent-input" /></label><label>Transport<input value={editing.transport || ''} onChange={e => setEditing({
              ...editing,
              transport: e.target.value
            })} data-testid="master-edit-transport-input" /></label></>}{editing.kind === 'volume' && <label>Pieces per set<input type="number" min="1" value={editing.pieces} onChange={e => setEditing({
            ...editing,
            pieces: e.target.value
          })} data-testid="master-edit-pieces-input" /></label>}<Button onClick={saveEdit} data-testid="save-master-edit"><Check size={16} /> Save changes</Button></div></div>}
  </div>;
}
